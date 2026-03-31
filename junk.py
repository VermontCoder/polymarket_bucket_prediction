from datetime import datetime, timedelta
import time

def seconds_until_next_five_min_interval():
    """
    Calculates the number of seconds from a given timestamp to the next 
    five-minute interval boundary (e.g., hh:00:00, hh:05:00, ..., hh:55:00).
    
    Args:
        now_timestamp: The current time, typically from datetime.now()
    
    Returns:
        The number of seconds (float) until the next five-minute interval.
    """
    
    # Calculate the total seconds from the epoch to the current time
    # using time.time() is efficient for this purpose
    timestamp = time.time()
    
    # The next 5-minute interval in seconds since the epoch is found 
    # by adding 300 seconds to the current timestamp and then using 
    # the modulo operator to find the remainder, which is subtracted
    # from the current time plus 300 seconds.
    interval_seconds = 300 # 5 minutes * 60 seconds/minute
    
    # The time of the next interval mark (since epoch)
    next_interval_timestamp = timestamp + interval_seconds - (timestamp % interval_seconds)
    
    # The difference is the time remaining
    seconds_remaining = next_interval_timestamp - timestamp
    
    # Alternatively, you can use datetime objects for clarity and the total_seconds() method:
    # now = datetime.fromtimestamp(timestamp)
    # next_interval = datetime.fromtimestamp(next_interval_timestamp)
    # seconds_remaining_dt = (next_interval - now).total_seconds()
    
    return seconds_remaining

# Example usage:
current_time = datetime.now()
seconds_to_wait = seconds_until_next_five_min_interval()

print(f"Current time: {current_time}")
print(f"Seconds until the next five-minute interval: {seconds_to_wait}")

# You can also see the exact time of the next interval
timestamp = time.time()
next_interval_timestamp = timestamp + 300 - (timestamp % 300)
next_interval_time = datetime.fromtimestamp(next_interval_timestamp)
print(f"Next five-minute interval time: {next_interval_time}")
