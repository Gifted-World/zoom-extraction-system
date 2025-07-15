"""
API Queue System for managing rate limits with Claude API.

This module provides a queue system to manage API requests and respect rate limits.
"""

import os
import time
import logging
import asyncio
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Callable, Awaitable
import anthropic

logger = logging.getLogger(__name__)

class TokenBucket:
    """
    Implements a token bucket algorithm for rate limiting.
    """
    def __init__(self, capacity: int, refill_rate: int):
        """
        Initialize the token bucket.
        
        Args:
            capacity: Maximum number of tokens the bucket can hold
            refill_rate: Number of tokens added per second
        """
        self.capacity = capacity
        self.refill_rate = refill_rate
        self.tokens = capacity
        self.last_refill = time.time()
        
    def refill(self):
        """Refill the bucket based on elapsed time."""
        now = time.time()
        elapsed = now - self.last_refill
        refill = elapsed * self.refill_rate
        self.tokens = min(self.capacity, self.tokens + refill)
        self.last_refill = now
        
    def consume(self, tokens: int) -> bool:
        """
        Try to consume tokens from the bucket.
        
        Args:
            tokens: Number of tokens to consume
            
        Returns:
            True if tokens were consumed, False otherwise
        """
        self.refill()
        if tokens <= self.tokens:
            self.tokens -= tokens
            return True
        return False
    
    def get_wait_time(self, tokens: int) -> float:
        """
        Calculate wait time needed for the requested tokens.
        
        Args:
            tokens: Number of tokens needed
            
        Returns:
            Seconds to wait for tokens to be available
        """
        self.refill()
        if tokens <= self.tokens:
            return 0
        
        additional_tokens_needed = tokens - self.tokens
        return additional_tokens_needed / self.refill_rate

class ClaudeAPIQueue:
    """
    Queue system for managing Claude API requests with rate limiting.
    """
    def __init__(self, tokens_per_minute: int = 30000):  # More conservative default limit
        """
        Initialize the API queue.
        
        Args:
            tokens_per_minute: Rate limit for tokens per minute
        """
        # Create token bucket with capacity for 1 minute and refill rate per second
        self.token_bucket = TokenBucket(tokens_per_minute, tokens_per_minute / 60)
        self.queue = []
        self.processing = False
        self.api_key = os.environ.get("CLAUDE_API_KEY")
        self.model = os.environ.get("CLAUDE_MODEL", "claude-3-opus-20240229")
        self.max_chunk_size = 15000  # Maximum token size for a single request
        
        if not self.api_key:
            logger.error("CLAUDE_API_KEY not found in environment variables")
            raise ValueError("CLAUDE_API_KEY not found in environment variables")
        
        self.client = anthropic.Anthropic(api_key=self.api_key)
        
    def estimate_tokens(self, text: str) -> int:
        """
        Estimate the number of tokens in a text.
        This is a rough estimate (4 chars ≈ 1 token).
        
        Args:
            text: Text to estimate tokens for
            
        Returns:
            Estimated token count
        """
        return len(text) // 4 + 1
    
    async def add_request(self, prompt: str, max_tokens: int = 4000, temperature: float = 0.2) -> str:
        """
        Add a request to the queue and wait for result.
        
        Args:
            prompt: The prompt to send to Claude
            max_tokens: Maximum tokens in the response
            temperature: Temperature for generation
            
        Returns:
            The response from Claude
        """
        # Create a future to be resolved when the request is processed
        loop = asyncio.get_running_loop()
        future = loop.create_future()
        
        # Estimate token usage
        estimated_tokens = self.estimate_tokens(prompt) + max_tokens
        
        # Check if we need to chunk the request
        if estimated_tokens > self.max_chunk_size:
            logger.info(f"Request exceeds max chunk size ({estimated_tokens} > {self.max_chunk_size}). Processing in chunks.")
            return await self._process_large_request(prompt, max_tokens, temperature)
        
        # Add to queue
        self.queue.append({
            "prompt": prompt,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "estimated_tokens": estimated_tokens,
            "future": future,
            "added_time": datetime.now()
        })
        
        # Log queue status
        queue_position = len(self.queue)
        logger.info(f"Request added to queue. Position: {queue_position}, Estimated tokens: {estimated_tokens}")
        
        # Start processing if not already running
        if not self.processing:
            asyncio.create_task(self._process_queue())
        
        # Wait for result
        return await future
    
    async def _process_large_request(self, prompt: str, max_tokens: int, temperature: float) -> str:
        """
        Process a large request by breaking it into smaller chunks.
        
        Args:
            prompt: The prompt to send to Claude
            max_tokens: Maximum tokens in the response
            temperature: Temperature for generation
            
        Returns:
            The combined response from Claude
        """
        # Extract system prompt if present (everything before the first user message)
        system_prompt = ""
        user_prompt = prompt
        
        if "Human:" in prompt:
            parts = prompt.split("Human:", 1)
            if len(parts) > 1:
                system_prompt = parts[0].strip()
                user_prompt = "Human:" + parts[1]
        
        # Split the user prompt into chunks
        chunk_size = self.max_chunk_size - self.estimate_tokens(system_prompt) - max_tokens
        chunks = self._split_text(user_prompt, chunk_size)
        
        logger.info(f"Split large request into {len(chunks)} chunks")
        
        results = []
        for i, chunk in enumerate(chunks):
            # Add context about chunking to each request
            if len(chunks) > 1:
                chunk_prompt = f"{system_prompt}\n\nThis is part {i+1} of {len(chunks)} of a larger document.\n\n{chunk}"
            else:
                chunk_prompt = f"{system_prompt}\n\n{chunk}"
            
            # Process chunk with standard queue
            logger.info(f"Processing chunk {i+1}/{len(chunks)}")
            
            # Create a future for this chunk
            loop = asyncio.get_running_loop()
            future = loop.create_future()
            
            # Add to queue
            estimated_tokens = self.estimate_tokens(chunk_prompt) + max_tokens
            self.queue.append({
                "prompt": chunk_prompt,
                "max_tokens": max_tokens,
                "temperature": temperature,
                "estimated_tokens": estimated_tokens,
                "future": future,
                "added_time": datetime.now()
            })
            
            # Start processing if not already running
            if not self.processing:
                asyncio.create_task(self._process_queue())
            
            # Wait for result
            chunk_result = await future
            results.append(chunk_result)
            
            # Add delay between chunks to avoid rate limits
            if i < len(chunks) - 1:
                delay = 5 + (estimated_tokens / 10000)  # Dynamic delay based on chunk size
                logger.info(f"Waiting {delay:.1f}s before processing next chunk")
                await asyncio.sleep(delay)
        
        # Combine results
        combined_result = "\n\n".join(results)
        return combined_result
    
    def _split_text(self, text: str, max_tokens: int) -> List[str]:
        """
        Split text into chunks of approximately max_tokens.
        Tries to split at paragraph boundaries when possible.
        
        Args:
            text: Text to split
            max_tokens: Maximum tokens per chunk
            
        Returns:
            List of text chunks
        """
        # Convert tokens to approximate character count
        max_chars = max_tokens * 4
        
        # If text is already small enough, return it as is
        if len(text) <= max_chars:
            return [text]
        
        chunks = []
        current_chunk = ""
        
        # Split by paragraphs first
        paragraphs = text.split("\n\n")
        
        for paragraph in paragraphs:
            # If adding this paragraph would exceed the limit
            if len(current_chunk) + len(paragraph) > max_chars:
                # If current chunk is not empty, add it to chunks
                if current_chunk:
                    chunks.append(current_chunk)
                    current_chunk = ""
                
                # If paragraph itself is too long, split it by sentences
                if len(paragraph) > max_chars:
                    sentences = paragraph.replace(". ", ".\n").split("\n")
                    for sentence in sentences:
                        if len(current_chunk) + len(sentence) > max_chars:
                            if current_chunk:
                                chunks.append(current_chunk)
                                current_chunk = ""
                            
                            # If sentence itself is too long, split it by words
                            if len(sentence) > max_chars:
                                words = sentence.split(" ")
                                for word in words:
                                    if len(current_chunk) + len(word) + 1 > max_chars:
                                        chunks.append(current_chunk)
                                        current_chunk = word + " "
                                    else:
                                        current_chunk += word + " "
                            else:
                                current_chunk = sentence + " "
                        else:
                            current_chunk += sentence + " "
                else:
                    current_chunk = paragraph + "\n\n"
            else:
                current_chunk += paragraph + "\n\n"
        
        # Add the last chunk if not empty
        if current_chunk:
            chunks.append(current_chunk)
        
        return chunks
    
    async def _process_queue(self):
        """Process the queue of API requests."""
        self.processing = True
        
        while self.queue:
            # Get the next request
            request = self.queue[0]
            estimated_tokens = request["estimated_tokens"]
            
            # Check if we have enough tokens
            wait_time = self.token_bucket.get_wait_time(estimated_tokens)
            
            if wait_time > 0:
                # Need to wait for tokens to refill
                wait_time_rounded = round(wait_time, 2)
                logger.info(f"Rate limit: Waiting {wait_time_rounded}s for token bucket to refill")
                await asyncio.sleep(wait_time)
            
            # Process the request
            try:
                # Remove from queue before processing to avoid double processing
                self.queue.pop(0)
                
                # Log processing start
                queue_length = len(self.queue)
                wait_time = (datetime.now() - request["added_time"]).total_seconds()
                logger.info(f"Processing request after {wait_time:.1f}s wait. Remaining queue: {queue_length}")
                
                # Consume tokens
                self.token_bucket.consume(estimated_tokens)
                
                # Make the API call
                response = await self._make_api_call(
                    request["prompt"],
                    request["max_tokens"],
                    request["temperature"]
                )
                
                # Resolve the future with the result
                request["future"].set_result(response)
                
                # Log success
                logger.info(f"Request processed successfully. Remaining queue: {len(self.queue)}")
                
            except Exception as e:
                logger.error(f"Error processing request: {e}")
                request["future"].set_exception(e)
        
        self.processing = False
    
    async def _make_api_call(self, prompt: str, max_tokens: int, temperature: float) -> str:
        """
        Make the actual API call to Claude.
        
        Args:
            prompt: The prompt to send
            max_tokens: Maximum tokens in the response
            temperature: Temperature for generation
            
        Returns:
            The response text from Claude
        """
        try:
            # Make the API call
            response = await asyncio.to_thread(
                self.client.messages.create,
                model=self.model,
                max_tokens=max_tokens,
                temperature=temperature,
                messages=[
                    {"role": "user", "content": prompt}
                ]
            )
            
            # Extract the response text
            return response.content[0].text
            
        except anthropic.RateLimitError as e:
            logger.warning(f"Rate limit exceeded: {e}")
            # Add additional wait time on rate limit errors
            await asyncio.sleep(30)  # Increased from 10s to 30s
            raise
        except Exception as e:
            logger.error(f"Error calling Claude API: {e}")
            raise

# Global instance for use throughout the application
api_queue = ClaudeAPIQueue() 