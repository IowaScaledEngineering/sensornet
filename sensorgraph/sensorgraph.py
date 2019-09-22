import requests
import argparse
import configparser
import json
import iso8601
import matplotlib.pyplot as plt 
import matplotlib.dates as mdates
import matplotlib.cbook as cbook
import sys
import datetime
import bisect
import pytz

def rounder(t):
  if t.minute > 0 or t.second > 0:
    return t.replace(second=0, microsecond=0, minute=0, hour=t.hour+1)

def find_le(a, x):
    i = bisect.bisect_right(a, x)
    if i:
        return i-1
    raise ValueError

def generateXAxisTimes(startDT, endDT, increment):
  x = [ ]
  # Normalize time to whole minutes
  incDT = startDT.astimezone(datetime.timezone.utc)
  endDTUTC = endDT.astimezone(datetime.timezone.utc)
  # We want roughly 2000 datapoints
  while incDT < endDTUTC:
    x.append(incDT)
    incDT = incDT + datetime.timedelta(seconds=increment)
  return x

def convertCtoF(temp_c):
  return (temp_c * 1.8) + 32

def fetchSensor(startDT, endDT, increment, xAxis, sensorName, conversionFunc=None):
  baseURL = 'http://localhost:8082/gethistory'
  url = '%s/%s' % (baseURL, sensorName)
  y = [ ]
  reqargs = { }
  reqargs['start'] = startDT.astimezone(datetime.timezone.utc).isoformat()
  reqargs['end'] = endDT.astimezone(datetime.timezone.utc).isoformat()
  reqargs['increment'] = increment  
  response = requests.get(url, reqargs)

  if response.status_code != 200:
    print("Failure - status code %d" % (response.status_code))
    # Fill retval with Nones
    for xTime in xAxis:
      y.append(None)
    return
  
  data = response.json()

  dtIndexes = []
  for element in data:
    dtIndexes.append(int(iso8601.parse_date(element['time']).astimezone(datetime.timezone.utc).timestamp()))

  for incDT in xAxis:
    val = None
    potentialVal = None
    potentialValDT = None

    try:
      potentialIdx = find_le(dtIndexes, int(incDT.timestamp()))
      val = float(data[potentialIdx]['value'])
    except Exception as e:
      pass
    if val is None:
      y.append(val)
    elif conversionFunc is not None:
      try:
        potentialVal = conversionFunc(val)
      except:
        potentialVal = val
      y.append(potentialVal)
    else:
      y.append(val)
  
  return y

def main(config):

  zone = 'America/Denver'
  tz = pytz.timezone(zone)
  plt.rcParams['timezone'] = zone

  endDT = rounder(datetime.datetime.utcnow().replace(tzinfo=datetime.timezone.utc))
  startDT = endDT - datetime.timedelta(days=1)
  
  print("Starting DT: %s" % (startDT))
  print("Ending DT: %s" % (endDT))
  
  totalSeconds = (endDT - startDT).total_seconds()
  targetDatapoints = 1000
  secondsPerDatapoint = max(1, int(totalSeconds / targetDatapoints))

  print("totalSeconds = %d, seconds per datapoint = %d" % (totalSeconds, secondsPerDatapoint))

  x = generateXAxisTimes(startDT, endDT, secondsPerDatapoint)
  y = fetchSensor(startDT, endDT, secondsPerDatapoint, x, 'house/basement/temperature', conversionFunc=convertCtoF)
  y2 = fetchSensor(startDT, endDT, secondsPerDatapoint, x, 'house/insulator_room/temperature', conversionFunc=convertCtoF)


  print("Starting graph generation")
  #sys.exit()
  fig, ax = plt.subplots()
  ax.format_xdata = mdates.DateFormatter('%H:%M')
  ax.xaxis.set_minor_locator(mdates.HourLocator())
  ax.xaxis.set_major_formatter(mdates.DateFormatter('%m/%d %H:%M'))
  fig.autofmt_xdate()
  plt.plot(x, y, color='red')
  plt.plot(x, y2)
  
  ticks = []
  labels = []
  for t in range(0, int(totalSeconds / (60 * 60))):
    tickDT = startDT + datetime.timedelta(hours=t)
    if ( tickDT.hour in [0,6,12,18] ):
      ticks.append(tickDT)
      labels.append(tickDT.astimezone(tz))

  plt.xticks(ticks)
  plt.grid(True)
  plt.xlabel('Time') 
  plt.ylabel('Deg C') 
  plt.title('My first graph!') 
  plt.ylim(0, 100)     # set the ylim to bottom, top
  plt.savefig("test.png")  
  print("Completed graph generation")

if __name__== "__main__":
  ap = argparse.ArgumentParser()
  ap.add_argument("-c", "--config", help="specify file with configuration", type=str)
  ap.set_defaults(config="sensorgraph.cfg")
  args = ap.parse_args()
  main(args.config)
