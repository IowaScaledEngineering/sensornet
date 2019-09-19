import threading
import datetime

class SensorStatus:
  sensorNodeTree = { }
  defaultTimezone = datetime.timezone.utc
  webdbConnectData = { }
  lock = threading.Lock()
  
  
sensorStatus = SensorStatus()

