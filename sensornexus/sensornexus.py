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
import pickle

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
import pytz

import atexit
import mysql.connector as mysql

# TO DO
# - Age out nodes that haven't been filled lately
# - Implement maximum update rate
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
      sensor = sensorStatus.sensorNodeTree[key]['data']
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
      output += "%s" % (sensorStatus.sensorNodeTree[path]['data'][0]['value'])
    else:
      output += "None"
    SensorStatus.sensorStatus.lock.release()
    
    return output

class ws_gethistory:
  def sortByDatetime(self, element):
    return element['time']
    
  def GET(self, path):
    output = ""
    args = web.input()
    outputlist = [ ]
    webdbConnectData = SensorStatus.sensorStatus.webdbConnectData
    # Get starting date/time
    try:
      startDT = iso8601.parse_date(args['start']).astimezone(tzinfo=datetime.timezone.utc)
      startTime = startDT.timestamp()
    except:
      # Assume 1 week of data
      startDT = datetime.datetime.utcnow().replace(tzinfo=datetime.timezone.utc) - datetime.timedelta(days=7)
      startTime = startDT.timestamp()

    print("Starting history at %s" % startDT.isoformat())

    # Get ending date/time
    try:
      endDT = iso8601.parse_date(args['end']).astimezone(tzinfo=datetime.timezone.utc)
      endTime = endDT.timestamp()
    except:
      # Assume now, giving us 1 week of data
      endDT = datetime.datetime.utcnow().replace(tzinfo=datetime.timezone.utc)
      endTime = endDT.timestamp()
    
    print("Ending history at %s" % endDT.isoformat())


    resultsTimezone = SensorStatus.sensorStatus.defaultTimezone
    if 'tz' in args:
      try:
        resultsTimezone = pytz.timezone(args['tz'])
      except:
        pass

    try:
      minIncrement = int(args['increment'])
    except:
      minIncrement = 1
      
    # Is this sensor in the database for our date range?  Try there first
    webDB = None
    if webdbConnectData['mysqlServer'] is not None and webdbConnectData['mysqlUsername'] is not None and webdbConnectData['mysqlPassword'] is not None:
      try:
        webDB = mysqldb(webdbConnectData['mysqlServer'], webdbConnectData['mysqlPort'], webdbConnectData['mysqlUsername'], webdbConnectData['mysqlPassword'], webdbConnectData['mysqlDatabaseName'])
        #print("Database connection succeeded")
        cursor = webDB.conn.cursor()
        query = "SELECT DATE_FORMAT(d.timestamp, '%Y-%m-%dT%TZ'), d.value FROM SensorData AS d INNER JOIN SensorNames AS n ON (d.nameID=n.nameID) WHERE n.sensorName=%s AND d.timestamp >= %s and d.timestamp <= %s ORDER BY d.timestamp"
        cursor.execute(query, (path, startDT.strftime("%Y-%m-%d %H:%M:%S.%f"), endDT.strftime("%Y-%m-%d %H:%M:%S.%f")))
        for (timestamp,value) in cursor:
          # all DB in UTC
          try:
            timeDT = iso8601.parse_date(timestamp).replace(tzinfo=datetime.timezone.utc)
            localTimeDT = timeDT.astimezone(resultsTimezone)
            element = {'time':localTimeDT.isoformat(), 'value':value}
            outputlist.append(element)
              
          except Exception as e:
            print("Database record [%s]=>[%s] failed\n" % (timestamp, value))
            print(e)
        cursor.close()
      except Exception as e:
        print(e)
      finally:
        try:
          webDB.conn.close()
        except:
          pass

    SensorStatus.sensorStatus.lock.acquire()
    sensorStatus = SensorStatus.sensorStatus

    if path in sensorStatus.sensorNodeTree:
      for entry in sensorStatus.sensorNodeTree[path]['data']:
        # All timestamps, as stored, are in UTC.  Make sure we read it and put UTC as the timezone
        timeDT = datetime.datetime.fromtimestamp(entry['time']).replace(tzinfo=datetime.timezone.utc)
        localTimeDT = timeDT.astimezone(resultsTimezone)

        if 'format' in args:
          timeStr = localTimeDT.strftime(args['format'])
        else:
          timeStr = localTimeDT.isoformat()
        
        element = {'time':timeStr, 'value':entry['value']}
        
        outputlist.append(element)

    SensorStatus.sensorStatus.lock.release()

    outputlist.sort(key = self.sortByDatetime)

    # Now, work through the outputlist and delete elements that do not make the minimum increment
    maxel = len(outputlist)
    i = 0
    lastTime = datetime.datetime.fromtimestamp(0).replace(tzinfo=datetime.timezone.utc)
    while i < maxel:
      thisTime = iso8601.parse_date(outputlist[i]['time'])
      if thisTime < lastTime + datetime.timedelta(seconds=minIncrement):
        del outputlist[i]
        maxel = len(outputlist)
      else:
        i = i + 1
        lastTime = thisTime

    output = json.dumps(outputlist)
    
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
    
    self.configOpts['sensorDataFile'] = self.parserGetWithDefault(parser, "global", "sensorDataFile", "sensordata.pickle")   

    self.configOpts['defaultTimezone'] = datetime.timezone.utc
    zone = self.parserGetWithDefault(parser, "global", "defaultTimezone", "America/Denver")
    try:
      self.configOpts['defaultTimezone'] = pytz.timezone(zone)
    except:
      print("Bad timezone [%s], defaulting to UTC" % self.configOpts['defaultTimezone'])
      self.configOpts['defaultTimezone'] = datetime.timezone.utc

    self.configOpts['mysqlUsername'] = self.parserGetWithDefault(parser, "global", "mysqlUsername", None)
    self.configOpts['mysqlPassword'] = self.parserGetWithDefault(parser, "global", "mysqlPassword", None)
    self.configOpts['mysqlServer'] = self.parserGetWithDefault(parser, "global", "mysqlServer", None)
    self.configOpts['mysqlPort'] = self.parserGetIntWithDefault(parser, "global", "mysqlServer", 3306)
    self.configOpts['mysqlDatabaseName'] = self.parserGetIntWithDefault(parser, "global", "mysqlDatabaseName", "sensornet")

    self.configOpts['mysqlReadOnlyUsername'] = self.parserGetWithDefault(parser, "global", "mysqlReadOnlyUsername", self.configOpts['mysqlUsername'])
    self.configOpts['mysqlReadOnlyPassword'] = self.parserGetWithDefault(parser, "global", "mysqlPassword", self.configOpts['mysqlPassword'])
   
    dblogging = self.parserGetWithDefault(parser, "global", "defaultDatabaseLogEnable", "false")
    if dblogging.casefold() == "true".casefold():
      self.configOpts['defaultDatabaseLogEnable'] = True
    else:
      self.configOpts['defaultDatabaseLogEnable'] = False
    
    self.configOpts['defaultDatabaseLogInterval'] = self.parserGetIntWithDefault(parser, "global", "defaultDatabaseLogInterval", 1)
    self.configOpts['defaultMemoryLogInterval'] = self.parserGetIntWithDefault(parser, "global", "defaultMemoryLogInterval", 1)
    self.configOpts['defaultMemoryLogDepth'] = self.parserGetIntWithDefault(parser, "global", "defaultMemoryLogDepth", 10)       
    
    self.configOpts['sensors'] = { }
    
    # Get sensors
    sections = parser.sections()
    REsensor = re.compile("(?P<type>[a-zA-Z0-9]+):(?P<sensorName>[a-zA-Z0-9_/]+)")
    for section in sections:
      print("Getting sensors from configuration")
      match = REsensor.match(section)
      
      if match is None:
        print("Ignoring section [%s]" % (section))
      elif match.groupdict()['type'] == 'sensor':
        print("Found sensor named [%s]" % (match.groupdict()['sensorName']))
        sensorName = match.groupdict()['sensorName']

        sensor = { 'name':sensorName }
        
        dblogging = self.parserGetWithDefault(parser, section, "databaseLogEnable", "false")
        if dblogging.casefold() == "true".casefold():
          sensor['databaseLogEnable'] = True
        else:
          sensor['databaseLogEnable'] = False

        sensor['databaseLogInterval'] = self.parserGetIntWithDefault(parser, section, "databaseLogInterval", self.configOpts['defaultDatabaseLogInterval'])

        sensor['memoryLogDepth'] = self.parserGetIntWithDefault(parser, section, "memoryLogDepth", self.configOpts['defaultMemoryLogDepth'])
        sensor['memoryLogInterval'] = self.parserGetIntWithDefault(parser, section, "memoryLogInterval", self.configOpts['defaultMemoryLogInterval'])
        
        if sensor['name'] in self.configOpts['sensors']:
          print("ERROR!  A sensor named %s is already configured" % (sensor['name']))
        else:
          self.configOpts['sensors'][sensor['name']] = sensor


def sensorsRetrieveOnStartup(pickleFilename):
  return pickle.load( open( pickleFilename, "rb" ) )
  
def sensorsSaveOnExit(sensorNodeTree, pickleFilename):
  pickle.dump( sensorNodeTree, open( pickleFilename, "wb" ) )


class mysqldb(object):
  conn = None
  hostname = 'localhost'
  port = 3306
  username = ''
  password = ''
  dbname = ''
  nameIDCache = { }
  lock = threading.Lock()
  
  def __init__(self, hostname, port, username, password, dbname):
    try:
      self.hostname = hostname
      self.port = port
      self.username = username
      self.password = password
      self.dbname = dbname
      self.reinit()
    except:
      pass
      
  def reinit(self):
    try:
      print("Trying to connect to mysql")
      self.conn = mysql.connect(host=self.hostname, port=self.port, user=self.username, passwd=self.password, database=self.dbname)
      print("mysql connect success")
    except Exception as e:
      print("mysql connect FAILURE")
      pass
      
  def getNameID(self, nameStr):
    # The easy way - get the nameID from cache
    if nameStr in self.nameIDCache:
      return self.nameIDCache[nameStr]
    
    if not self.conn.is_connected():
      # Ping will automagically attempt reconnections
      #print("mysql not connected, trying ping to restart")
      try:
        self.conn.ping(reconnect=True, attempts=2, delay=1)
      except InterfaceError:
        pass
    
    if not self.conn.is_connected():
      #print("still not connected, dying")
      raise InterfaceError
    
    retval = 0
    
    try:
      cursor = self.conn.cursor()
      #print("starting new select")
      query = "SELECT nameID FROM SensorNames WHERE sensorName=%s;"
      cursor.execute(query, (nameStr,))
      
      for (nameID,) in cursor:
        self.nameIDCache[nameStr] = nameID
        retval = int(nameID)
        break


      if 0 == retval:
        #print("name doesn't exist, do something")
        query = "INSERT INTO SensorNames (nameID,sensorName) VALUES (0,%s);"
        cursor.execute(query, (nameStr,))
        self.conn.commit()
        query = "SELECT nameID FROM SensorNames WHERE sensorName=%s"
        cursor.execute(query, (nameStr,))
        for (nameID,) in cursor:
          self.nameIDCache[nameStr] = nameID
          retval = int(nameID)
          break
      
      cursor.close()
      
      if retval != 0:
        return retval
      else:
        raise InterfaceError
      
    except Exception as e:
      print("Exception in getNameID")
      print(e)
      raise InterfaceError

  def insertSensorData(self, nameStr, timestamp, datavalue):
    if not self.conn.is_connected():
      # Ping will automagically attempt reconnections
      print("mysql not connected, trying ping to restart")
      try:
        self.conn.ping(reconnect=True, attempts=2, delay=1)
      except InterfaceError:
        pass
    
    if not self.conn.is_connected():
      print("still not connected, dying")
      raise InterfaceError
    
    nameID = self.getNameID(nameStr)
    
    try:
      #YYYY-MM-DD hh:mm:ss
      timestampStr = timestamp.strftime("%Y-%m-%d %H:%M:%S.%f")
      
      cursor = self.conn.cursor()
      query = "INSERT INTO SensorData (nameID,timestamp,value) VALUES (%s, %s, %s);"
      cursor.execute(query, (nameID, timestamp, datavalue))
      self.conn.commit()
      cursor.close()
      
    except Exception as e:
      print("Exception in insertSensorData")
      print(e)
      raise InterfaceError

def mqtt_onMessage(client, userdata, message):
  payload = message.payload.decode()
  sensorName = message.topic
  lastUpdate = time.time()
  
  print("Message [%s]: %s" % (sensorName, payload))

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
    measurementDT = datetime.datetime.utcnow()
    measurementTime = measurementDT.timestamp()

  print("Inserting data - [%s]=>%s" % (sensorName, decodedValues));

  thisEntry = {'value':decodedValues['value'], 'time':measurementTime }

  # At this point the message is good and validated
  # Now we acquire a lock for as little time as possible
  try:
    if sensorName in userdata['gConf'].configOpts['sensors']:
      maxLen = userdata['gConf'].configOpts['sensors'][sensorName]['memoryLogDepth']
      minInterval = userdata['gConf'].configOpts['sensors'][sensorName]['memoryLogInterval']
      dbLog = userdata['gConf'].configOpts['sensors'][sensorName]['databaseLogEnable']
      dbMinInterval = userdata['gConf'].configOpts['sensors'][sensorName]['databaseLogInterval']
    else:
      maxLen = userdata['gConf'].configOpts['defaultMemoryLogDepth']
      minInterval = userdata['gConf'].configOpts['defaultMemoryLogInterval']
      dbLog = userdata['gConf'].configOpts['defaultDatabaseLogEnable']
      dbMinInterval = userdata['gConf'].configOpts['defaultDatabaseLogInterval']
  except Exception as e:
    print(e)

  # Make sure sensor is in the node tree, and if not, add it.
  # This saves a bunch of spaghetti logic later on in the data storage and DB code
  userdata['sensorStatus'].lock.acquire()
  sensorNodeTree = userdata['sensorStatus'].sensorNodeTree
  if message.topic not in sensorNodeTree:    
    sensorNodeTree[message.topic] = { }
    sensorNodeTree[message.topic]['meta'] = { } # Metadata is a dictionary of various meta about the readings
    sensorNodeTree[message.topic]['data'] = [ ] # Data is a list of readings by clock order
  userdata['sensorStatus'].lock.release()

  
  # Update sensor reading array in database
  timeToWriteToDB = False
  if dbLog:
    # Get a lock so we can go get the last DB write
    userdata['sensorStatus'].lock.acquire()
    try:
      sensorNodeTree = userdata['sensorStatus'].sensorNodeTree

      if 'lastDBWrite' not in sensorNodeTree[message.topic]['meta']:
        sensorNodeTree[message.topic]['meta']['lastDBWrite'] = 0
        
      if sensorNodeTree[message.topic]['meta']['lastDBWrite'] + dbMinInterval <= measurementTime:
        timeToWriteToDB = True
    except:
      pass
    finally:
      userdata['sensorStatus'].lock.release()

    # Only add to DB if we are past the minimum interval
    if timeToWriteToDB:
      try:
        mysql = userdata['dbConnection']
        mysql.insertSensorData(sensorName, measurementDT, decodedValues['value'])
      except:
        print("Error: failed DB stuff, going on")
        # We didn't write, so don't update the time
        timeToWriteToDB = False 


  # Update sensor reading array in memory
  try:
    userdata['sensorStatus'].lock.acquire()
    sensorNodeTree = userdata['sensorStatus'].sensorNodeTree
    
    # Opportunistically use this lock to update the last DB measurement time
    if timeToWriteToDB is True:
      sensorNodeTree[message.topic]['meta']['lastDBWrite'] = measurementTime
    
    if len(sensorNodeTree[message.topic]['data']) == 0:
      sensorNodeTree[message.topic]['data'].insert(0, thisEntry)
    # Don't insert entries older than the most current and make sure they exceed the minimum
    # memory log interval
    elif ( thisEntry['time'] > sensorNodeTree[message.topic]['data'][0]['time']
      and sensorNodeTree[message.topic]['data'][0]['time'] + minInterval <= measurementTime ):
      sensorNodeTree[message.topic]['data'].insert(0, thisEntry)

    while len(sensorNodeTree[message.topic]['data']) > maxLen:
      sensorNodeTree[message.topic]['data'].pop()
      
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
  sensorStatus.defaultTimezone = gConf.configOpts['defaultTimezone']
  sensorStatus.webdbConnectData['mysqlServer'] = gConf.configOpts['mysqlServer']
  sensorStatus.webdbConnectData['mysqlPort'] = gConf.configOpts['mysqlPort']
  sensorStatus.webdbConnectData['mysqlUsername'] = gConf.configOpts['mysqlReadOnlyUsername']
  sensorStatus.webdbConnectData['mysqlPassword'] = gConf.configOpts['mysqlReadOnlyPassword']
  sensorStatus.webdbConnectData['mysqlDatabaseName'] = gConf.configOpts['mysqlDatabaseName']
  
  
  try:
    lastNodeTree = sensorsRetrieveOnStartup( gConf.configOpts['sensorDataFile'] )
    sensorStatus.sensorNodeTree = lastNodeTree
  except:
    pass
    
  atexit.register(sensorsSaveOnExit, sensorNodeTree=sensorStatus.sensorNodeTree, pickleFilename=gConf.configOpts['sensorDataFile'] )
  
  app = web.application(urlHandlers, globals())
  httpserver = web.httpserver

  mqttDB = None
  if gConf.configOpts['mysqlServer'] is not None and gConf.configOpts['mysqlUsername'] is not None and gConf.configOpts['mysqlPassword'] is not None:
    try:
      mqttDB = mysqldb(gConf.configOpts['mysqlServer'], gConf.configOpts['mysqlPort'], gConf.configOpts['mysqlUsername'], gConf.configOpts['mysqlPassword'], gConf.configOpts['mysqlDatabaseName'])
      print("Database connection succeeded")
    except:
      print("Database connection failed")
      mqttDB = None


  mqtt.Client.connected_flag = False
  mqttClient = mqtt.Client(userdata={'sensorStatus':sensorStatus, 'gConf':gConf, 'dbConnection':mqttDB})
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
      mqttClient.loop_stop()
      
      try:
        if mqttDB is not None:
          mqttDB.close()
      except:
        pass
      
      
      if httpserver.server:
        httpserver.server.stop()
        httpserver.server = None
      
      mqttClient.disconnect()
      sys.exit()

    except Exception as e:
      print("Unhandled exception")
      print(e)
      mqttClient.loop_stop()

      try:
        if mqttDB is not None:
          mqttDB.close()
      except:
        pass

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

