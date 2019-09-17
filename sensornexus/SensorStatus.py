import threading
import datetime

class SensorStatus:
  sensorNodeTree = { }
  defaultTimezone = datetime.timezone.utc
  lock = threading.Lock()
  
sensorStatus = SensorStatus()

