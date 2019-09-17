# *************************************************************************
# Title:    MRBus/MRBee to Home Sensor Network Bridge 
# Authors:  Nathan D. Holmes <maverick@drgw.net>
#           Michael D. Petersen <railfan@drgw.net>
# File:     sensor-bridge.py
# License:  GNU General Public License v3
#
# LICENSE:
#   Copyright (C) 2019 Michael Petersen & Nathan Holmes
#    
#   This program is free software; you can redistribute it and/or modify
#   it under the terms of the GNU General Public License as published by
#   the Free Software Foundation; either version 3 of the License, or
#   any later version.
#
#   This program is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty of
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#   GNU General Public License for more details.
#
# DESCRIPTION:
#
#*************************************************************************

import sys
import time
import traceback
import socket
import argparse
import configparser
import re
import struct
from simpleeval import simple_eval
import datetime
try:
  import web
except ImportError:
   raise ImportError('web.py is missing - you probably need to use pip3 to install utils, db, and web.py - be sure to install the 0.40-dev1 version')

import _thread as thread
import paho.mqtt.client as mqtt
import threading
import SensorStatus
import json
import iso8601

# TO DO
# - Age out nodes that haven't been filled lately
# - Store selected nodes to database
# - Implement maximum update rate
# - Implement queue for holding last X values
# - Implement configuration file

class ws_status:        
  def GET(self, args):
    sensorStatus = SensorStatus.sensorStatus
    
    return output

class ws_nodelist:
  def GET(self):
    output = ""
    args = web.input()
    
    SensorStatus.sensorStatus.lock.acquire()
    sensorStatus = SensorStatus.sensorStatus
    keys = sorted(sensorStatus.sensorNodeTree.keys())
    for key in keys:
      sensor = sensorStatus.sensorNodeTree[key]
      output += "%s = %s\n" % (key, sensor[0]['value'])
    SensorStatus.sensorStatus.lock.release()
    return output

class ws_getval:
  def GET(self, path):
    output = ""
    args = web.input()
    
    SensorStatus.sensorStatus.lock.acquire()
    sensorStatus = SensorStatus.sensorStatus
    if path in sensorStatus.sensorNodeTree:
      output += "%s" % (sensorStatus.sensorNodeTree[path][0]['value'])
    else:
      output += "None"
    SensorStatus.sensorStatus.lock.release()
    
    return output

class ws_gethistory:
  def GET(self, path):
    output = ""
    args = web.input()
    
    SensorStatus.sensorStatus.lock.acquire()
    sensorStatus = SensorStatus.sensorStatus
    
    if path in sensorStatus.sensorNodeTree:
      for entry in sensorStatus.sensorNodeTree[path]:
        if 'format' in args:
          timeVal = time.gmtime(entry['time'])
          timeStr = time.strftime(args['format'], timeVal)
        else:
          timeStr = datetime.datetime.fromtimestamp(entry['time']).replace(tzinfo=datetime.timezone.utc).isoformat()

        output += "%s,%s\n" % (timeStr, entry['value'])
    else:
      output += "None"
    SensorStatus.sensorStatus.lock.release()
    
    return output

urlHandlers = (
  '/nodelist', 'ws_nodelist',
  '/getval/(.*)', 'ws_getval',
  '/gethistory/(.*)', 'ws_gethistory'
)


def runWebserver(httpserver, app, serverAddress):
  return httpserver.runsimple(app.wsgifunc(), serverAddress)

def mqtt_onConnect(client, userdata, flags, rc):
  if rc == 0:
    # Successful Connection
    print("Successful MQTT Connection")
    client.connected_flag = True
  elif rc == 1:
    print("ERROR: MQTT Incorrect Protocol Version")
    client.connected_flag = False
  elif rc == 2:
    print("ERROR: MQTT Invalid Client ID")
    client.connected_flag = False
  elif rc == 3:
    print("ERROR: MQTT Broker Unavailable")
    client.connected_flag = False
  elif rc == 4:
    print("ERROR: MQTT Bad Username/Password")
    client.connected_flag = False
  elif rc == 5:
    print("ERROR: MQTT Not Authorized")
    client.connected_flag = False
  else:
    print("ERROR: MQTT Other Failure %d" % (rc))
    client.connected_flag = False
  
  mqttClient.subscribe("#", qos=1)

def mqtt_onDisconnect(client, userdata, rc):
   print("MQTT disconnected - reason: [%s]" % (str(rc)))
   client.connected_flag = False


class GlobalConfiguration:
  sensors = None
  configOpts = None
  historicMaxDepth = None
  
  def __init__(self):
    self.sensors = { }
    self.configOpts = { }
    self.historicMaxDepth = { }
    
  def parserGetWithDefault(self, parser, section, key, defaultValue):
    try:
      value = parser.get(section, key)
      if value is None:
        value = defaultValue
    except:
      value = defaultValue

    return value

  def parserGetIntWithDefault(self, parser, section, key, defaultValue):
    try:
      value = parser.getint(section, key)
      if value is None:
        value = defaultValue
    except:
      value = defaultValue
    return value


  def loadConfiguration(self, confFilename):
    # Reinitialize
    self. __init__()
      
    print("Reading configuration file [%s]" % (confFilename))
    parser = configparser.SafeConfigParser()
    parser.read(confFilename)
    print("Configuration file successfully read")

    # Get global options
    self.configOpts['mqttBroker'] = self.parserGetWithDefault(parser, "global", "mqttServer", "localhost")
    self.configOpts['mqttPort'] = self.parserGetIntWithDefault(parser, "global", "mqttPort", 1883)
    self.configOpts['mqttUsername'] = self.parserGetWithDefault(parser, "global", "mqttUsername", None)
    self.configOpts['mqttPassword'] = self.parserGetWithDefault(parser, "global", "mqttPassword", None)
    self.configOpts['mqttReconnectInterval'] = self.parserGetIntWithDefault(parser, "global", "mqttReconnectInterval", 10)
    self.configOpts['defaultHistoricDepth'] = self.parserGetIntWithDefault(parser, "global", "defaultHistoricDepth", 10)   

def mqtt_onMessage(client, userdata, message):
  payload = message.payload.decode()
  sensor = message.topic
  lastUpdate = time.time()
  
  print("Message [%s]: %s" % (sensor, payload))

  try:
    decodedValues = json.loads(payload)
  except:
    print("Bogus message, json did not parse, ignoring")
    return

  # We only accept update type packets
  if 'type' not in decodedValues or decodedValues['type'] != 'update':
    return

  # If there's no value, there's no value to post
  if 'value' not in decodedValues or len(decodedValues['value']) == 0:
    return

  measurementTime = time.time()
  
  if False and 'time' in decodedValues:
    try:
      measurementDT = iso8601.parse_date(decodedValues['time'])
      measurementTime = measurementDT.timestamp()
    except:
      # Bad time, don't store
      print("Bogus timestamp")
      return
  else:
    measurementTime = datetime.datetime.utcnow().timestamp()

  print("Inserting data - [%s]=>%s" % (sensor, decodedValues));

  thisEntry = {'value':decodedValues['value'], 'time':measurementTime }

  userdata['sensorStatus'].lock.acquire()
  
  try:
    sensorNodeTree = userdata['sensorStatus'].sensorNodeTree
  
    if message.topic not in sensorNodeTree:
      sensorNodeTree[message.topic] = [ thisEntry ]
    else:
      # Don't insert entries older than the most current
      if thisEntry['time'] > sensorNodeTree[message.topic][0]['time']:
        sensorNodeTree[message.topic].insert(0, thisEntry)
  
    if message.topic in userdata['gConf'].historicMaxDepth:
      maxLen = userdata['gConf'].historicMaxDepth[message.topic]
    else:
      maxLen = userdata['gConf'].configOpts['defaultHistoricDepth']
  
    while len(sensorNodeTree[message.topic]) > maxLen:
      sensorNodeTree[message.topic].pop()
  except Exception as e:
    print("mqtt_onMessage got exception")
    print(e)
  finally:
    userdata['sensorStatus'].lock.release()

def main(configFile):
  # Global sensor status object - jointly used by MQTT and webserver, must be locked
  sensorStatus = SensorStatus.sensorStatus
  gConf = GlobalConfiguration()
  gConf.loadConfiguration(configFile)

  app = web.application(urlHandlers, globals())
  httpserver = web.httpserver
  
  defaultDataDepth = 1
  minInterval = 30
    
  mqtt.Client.connected_flag = False
  mqttClient = mqtt.Client(userdata={'sensorStatus':sensorStatus, 'gConf':gConf})
  mqttClient.on_connect=mqtt_onConnect
  mqttClient.on_disconnect=mqtt_onDisconnect
  mqttClient.on_message = mqtt_onMessage
  if gConf.configOpts['mqttUsername'] is not None and gConf.configOpts['mqttPassword'] is not None:
    mqttClient.username_pw_set(username=gConf.configOpts['mqttUsername'], password=gConf.configOpts['mqttPassword'])
  

  thread.start_new_thread(runWebserver, (httpserver, app, ('0.0.0.0', 8082)))
  print("Webserver started")

  lastMQTTConnectAttempt = None

  while True:
    try:
      # Reconnect MQTT client if necessary
      if mqttClient.connected_flag is False and (lastMQTTConnectAttempt is None or lastMQTTConnectAttempt + gConf.configOpts['mqttReconnectInterval'] < time.time()):
        # We don't have an MQTT client and need to try reconnecting
        try:
          lastMQTTConnectAttempt = time.time()
          mqttClient.loop_start()
          mqttClient.connect(gConf.configOpts['mqttBroker'], gConf.configOpts['mqttPort'], keepalive=60)
          while not mqttClient.connected_flag: 
            time.sleep(2) # Wait for callback to fire

          if mqttClient.connected_flag is True:
            mqttClient.subscribe("#", qos=1)
          mqttClient.loop_stop()
        except(KeyboardInterrupt):
          raise
        except:
          mqttClient.connected_flag = False

      if mqttClient.connected_flag is False:
        continue

      mqttClient.loop_start()
      time.sleep(0.01)

      
      
    except KeyboardInterrupt:
      print("User requested program termination, exiting...")
      if httpserver.server:
        httpserver.server.stop()
        httpserver.server = None
      mqttClient.disconnect()
      sys.exit()

    except Exception as e:
      print("Unhandled exception")
      print(e)
      if httpserver.server:
        httpserver.stop()
        httpserver.server = None
      mqttClient.disconnect()
      raise
 
if __name__== "__main__":
  ap = argparse.ArgumentParser()
  ap.add_argument("-c", "--config", help="specify file with configuration", type=str)
  ap.set_defaults(config="sensornexus.cfg")
  args = ap.parse_args()
  main(args.config)

