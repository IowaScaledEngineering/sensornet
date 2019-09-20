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

def main(config):
  baseURL = 'http://localhost:8082/gethistory'
  sensor = 'work/basement/temperature'
  url = '%s/%s' % (baseURL, sensor)
  zone = 'America/Denver'
  tz = pytz.timezone(zone)
  endDT = rounder(datetime.datetime.utcnow().replace(tzinfo=datetime.timezone.utc))
  startDT = endDT - datetime.timedelta(days=7)
  
  print("Starting DT: %s" % (startDT))
  print("Ending DT: %s" % (endDT))
  
  totalSeconds = (endDT - startDT).total_seconds()
  targetDatapoints = 1000
  secondsPerDatapoint = max(1, int(totalSeconds / targetDatapoints))

  print("totalSeconds = %d, seconds per datapoint = %d" % (totalSeconds, secondsPerDatapoint))

  reqargs = { }
  reqargs['start'] = startDT.astimezone(datetime.timezone.utc).isoformat()
  reqargs['end'] = endDT.astimezone(datetime.timezone.utc).isoformat()
  reqargs['increment'] = secondsPerDatapoint  
  response = requests.get(url, reqargs)

  if response.status_code != 200:
    print("Failure - status code %d" % (response.status_code))
    sys.exit()
  
  data = response.json()
  x = [ ]
  y = [ ]

  dtIndexes = []
  for element in data:
    dtIndexes.append(int(iso8601.parse_date(element['time']).astimezone(datetime.timezone.utc).timestamp()))

  # Normalize time to whole minutes
  incDT = startDT.astimezone(datetime.timezone.utc)
  endDTUTC = endDT.astimezone(datetime.timezone.utc)
  
  # We want roughly 2000 datapoints
  while incDT < endDTUTC:
    x.append(incDT)
    val = None
    potentialVal = None
    potentialValDT = None

    try:
      potentialIdx = find_le(dtIndexes, int(incDT.timestamp()))
      val = float(data[potentialIdx]['value'])
    except Exception as e:
      pass

    y.append(val)

    incDT = incDT + datetime.timedelta(seconds=secondsPerDatapoint)

  print("Starting graph generation")
  #sys.exit()
  fig, ax = plt.subplots()
  ax.format_xdata = mdates.DateFormatter('%m/%d %H:%M')
  fig.autofmt_xdate()
  ax.xaxis.set_minor_locator(mdates.HourLocator())
  plt.plot(x, y)
  
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
  plt.ylim(0, 35)     # set the ylim to bottom, top
  plt.savefig("test.png")  

if __name__== "__main__":
  ap = argparse.ArgumentParser()
  ap.add_argument("-c", "--config", help="specify file with configuration", type=str)
  ap.set_defaults(config="sensorgraph.cfg")
  args = ap.parse_args()
  main(args.config)
