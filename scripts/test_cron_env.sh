#!/bin/bash
# Script to test the cron environment

# Output the date
date > /Users/rajeshpanchanathan/Documents/genwise/projects/Insights_from_Online_Courses/logs/cron_env_test.log

# Output PATH
echo "PATH: $PATH" >> /Users/rajeshpanchanathan/Documents/genwise/projects/Insights_from_Online_Courses/logs/cron_env_test.log

# Try to find python
which python >> /Users/rajeshpanchanathan/Documents/genwise/projects/Insights_from_Online_Courses/logs/cron_env_test.log 2>&1

# List python versions
echo "Python versions:" >> /Users/rajeshpanchanathan/Documents/genwise/projects/Insights_from_Online_Courses/logs/cron_env_test.log
/usr/bin/python --version >> /Users/rajeshpanchanathan/Documents/genwise/projects/Insights_from_Online_Courses/logs/cron_env_test.log 2>&1
/usr/bin/python3 --version >> /Users/rajeshpanchanathan/Documents/genwise/projects/Insights_from_Online_Courses/logs/cron_env_test.log 2>&1
/Users/rajeshpanchanathan/miniforge3/bin/python --version >> /Users/rajeshpanchanathan/Documents/genwise/projects/Insights_from_Online_Courses/logs/cron_env_test.log 2>&1 