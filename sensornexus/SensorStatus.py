import threading
import datetime

class SensorStatus:
  sensorNodeTree = { }
  logger = None
  defaultTimezone = datetime.timezone.utc
  webdbConnectData = { }
  lock = threading.Lock()
  
sensorStatus = SensorStatus()

