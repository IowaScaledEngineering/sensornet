import requests
import argparse
import configparser
import json
import iso8601
import matplotlib.pyplot as plt 
import sys

def main(config):
  baseURL = 'http://localhost:8082/gethistory'
  sensor = 'work/basement/temperature'
  url = '%s/%s' % (baseURL, sensor)

  reqargs = { }  
  reqargs['start'] = '2019-09-10T00:00:00Z'
  reqargs['end'] = '2019-09-20T00:00:00Z'  
  reqargs['increment'] = 60  
  response = requests.get(url, reqargs)

  if response.status_code != 200:
    print("Failure - status code %d" % (response.status_code))
    sys.exit()
  
  #print(response.json())
  
  data = response.json()
  x = [ ]
  y = [ ]
  for element in data:
    print("%s = %s" % (element['time'], element['value']))
    measurementDT = iso8601.parse_date(element['time'])
    x.append(measurementDT)
    y.append(float(element['value']))

  plt.plot(x, y)
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
