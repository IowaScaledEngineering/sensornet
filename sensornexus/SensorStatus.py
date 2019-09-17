import threading

class SensorStatus:
  sensorNodeTree = { }
  lock = threading.Lock()
  
sensorStatus = SensorStatus()

