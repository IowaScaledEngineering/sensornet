# *************************************************************************
# Title:    MRBus/MRBee to Home Sensor Network Bridge 
# Authors:  Nathan D. Holmes <maverick@drgw.net>
#           Michael D. Petersen <railfan@drgw.net>
# File:     sensorbridge-mrbus.py
# License:  GNU General Public License v3
#
# LICENSE:
#   Copyright (C) 2019 Nathan Holmes & Michael Petersen
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
import math
import struct
import requests
from simpleeval import simple_eval
import datetime
import paho.mqtt.client as mqtt
import json
import logging
import daemonize
import sys, os, time

def mqtt_onConnect(client, userdata, flags, rc):
   logger = userdata['logger']
   
   if rc == 0:
      # Successful Connection
      logger.info("Successful MQTT Connection")
      client.connected_flag = True
   elif rc == 1:
      logger.error("ERROR: MQTT Incorrect Protocol Version")
      client.connected_flag = False
   elif rc == 2:
      logger.error("ERROR: MQTT Invalid Client ID")
      client.connected_flag = False
   elif rc == 3:
      logger.error("ERROR: MQTT Broker Unavailable")
      client.connected_flag = False
   elif rc == 4:
      logger.error("ERROR: MQTT Bad Username/Password")
      client.connected_flag = False
   elif rc == 5:
      logger.error("ERROR: MQTT Not Authorized")
      client.connected_flag = False
   else:
      logger.error("ERROR: MQTT Other Failure %d" % (rc))
      client.connected_flag = False

def mqtt_onDisconnect(client, userdata, rc):
   logger = userdata['logger']
   userdat
   logger.warning("MQTT disconnected - reason: [%s]" % (str(rc)))
   client.connected_flag = False

def getMillis():
   return time.time() * 1000.0

class globalConfiguration:
   sensors = None
   configOpts = None

   def __init__(self):
      self.sensors = { }
      self.configOpts = { }
      self.logger = logging.getLogger('main')

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

   def logLevelToVal(self, logLevel, default):
      logLevelValues = { 'error':logging.ERROR, 'warning':logging.WARNING, 'info':logging.INFO, 'debug':logging.DEBUG }      
      logLevel = logLevel.lower()
      if logLevel in logLevelValues:
         return logLevelValues[logLevel]
      return default


   def setupLogger(self, logFile, consoleLogLevel, fileLogLevel):
      self.logger = logging.getLogger('main')
      self.logger.setLevel(logging.DEBUG)
      fh = logging.FileHandler(self.configOpts['logFile'])
      fh.setLevel(self.logLevelToVal(fileLogLevel, logging.DEBUG))
      
      ch = logging.StreamHandler()
      ch.setLevel(self.logLevelToVal(consoleLogLevel, logging.DEBUG))
      
      logFileFormatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
      fh.setFormatter(logFileFormatter)
      ch.setFormatter(logFileFormatter)
      
      self.logger.addHandler(fh)
      self.logger.addHandler(ch)

   def loadConfiguration(self, confFilename, isDaemon=False, logFile=None, workingDir='.'):
      # Reinitialize
      self. __init__()
      
      if not isDaemon:
         print("Reading configuration file [%s]" % (confFilename))
      parser = configparser.SafeConfigParser()
      parser.read(confFilename)
      if not isDaemon:
         print("Configuration file successfully read")

      if isDaemon:
         logFileDefault = os.path.abspath('/tmp/sensorbridge-neurio.log')
      else:
         logFileDefault = os.path.abspath('%s/sensorbridge-neurio.log' % (workingDir))

      if logFile is not None:
         self.configOpts['logFile'] = os.path.abspath(logFile)
      else:
         self.configOpts['logFile'] = self.parserGetWithDefault(parser, "global", "logFile", logFileDefault)

      # This is where logging gets set up
      self.configOpts['consoleLogLevel'] = self.parserGetWithDefault(parser, "global", "consoleLogLevel", "error").lower()
      self.configOpts['fileLogLevel'] = self.parserGetWithDefault(parser, "global", "fileLogLevel", "debug").lower()
      self.setupLogger(self.configOpts['logFile'], self.configOpts['consoleLogLevel'], self.configOpts['fileLogLevel'])
      
      
      self.logger.info("---------------------------------------------------------------------------")
      self.logger.info("Logging startup at %s", datetime.datetime.utcnow().replace(tzinfo=datetime.timezone.utc).isoformat())

      # Get global options
      self.configOpts['sourceName'] = self.parserGetWithDefault(parser, "global", "sourceName", "sensorbridge-neurio")
      self.configOpts['locale'] = self.parserGetWithDefault(parser, "global", "locale", "house")
      self.configOpts['neurioName'] = self.parserGetWithDefault(parser, "global", "neurioName", "main_panel")
      self.configOpts['mqttBroker'] = self.parserGetWithDefault(parser, "global", "mqttServer", "localhost")
      self.configOpts['mqttPort'] = self.parserGetIntWithDefault(parser, "global", "mqttPort", 1883)
      self.configOpts['mqttUsername'] = self.parserGetWithDefault(parser, "global", "mqttUsername", None)
      self.configOpts['mqttPassword'] = self.parserGetWithDefault(parser, "global", "mqttPassword", None)
      self.configOpts['mqttReconnectInterval'] = self.parserGetIntWithDefault(parser, "global", "mqttReconnectInterval", 10)
      self.configOpts['neurioAddress'] = self.parserGetWithDefault(parser, "global", "neurioAddress", None)
      self.configOpts['postInterval'] = self.parserGetIntWithDefault(parser, "global", "postInterval", 10)
import signal

class SignalHandler():
    def __init__(self):
       self.terminate = False
       self.reparse = False

    def signalHandlerTerminate(self, signal, frame):
       self.terminate = True
   

def main(mainParms):
   # Unpack incoming parameters
   # mainParms = {'startupDirectory': pwd, 'configFile': configFile, 'serialPort': args.serial, 'isDaemon':isDaemon, 'logFile':args.logfile }
   
   gConf = globalConfiguration();
   gConf.loadConfiguration(mainParms['configFile'], logFile=mainParms['logFile'], workingDir=mainParms['startupDirectory'], isDaemon=mainParms['isDaemon'])

   # Get logger
   logger = gConf.logger

   signalHandler = SignalHandler();

   mqtt.Client.connected_flag = False
   mqttClient = mqtt.Client(userdata={'logger':logger})
   mqttClient.on_connect=mqtt_onConnect
   mqttClient.on_disconnect=mqtt_onDisconnect
   if gConf.configOpts['mqttUsername'] is not None and gConf.configOpts['mqttPassword'] is not None:
      mqttClient.username_pw_set(username=gConf.configOpts['mqttUsername'], password=gConf.configOpts['mqttPassword'])

   # Initialization

   lastPacket = getMillis() - 1000.0
   lastMQTTConnectAttempt = None

   logger.info("Starting run phase")
   
   signal.signal(signal.SIGINT, signalHandler.signalHandlerTerminate)
   signal.signal(signal.SIGTERM, signalHandler.signalHandlerTerminate)
   #signal.signal(signal.SIGKILL, signalHandler.signalHandler)
   
   # Main Run Loop - runs until something weird happens
   try:
      while True:
         if signalHandler.terminate:
            raise KeyboardInterrupt
         
         # Reconnect MQTT client if necessary
         if mqttClient.connected_flag is False and (lastMQTTConnectAttempt is None or lastMQTTConnectAttempt + gConf.configOpts['mqttReconnectInterval'] < time.time()):
            # We don't have an MQTT client and need to try reconnecting
            try:
               lastMQTTConnectAttempt = time.time()
               mqttClient.loop_start()
               mqttClient.connect(gConf.configOpts['mqttBroker'], gConf.configOpts['mqttPort'], keepalive=60)
               while not mqttClient.connected_flag: 
                  time.sleep(0.01) # Wait for callback to fire
               mqttClient.loop_stop()
            except(KeyboardInterrupt):
               raise
            except:
               mqttClient.connected_flag = False

         try:
            # Start allowing MQTT callbacks
            mqttClient.loop_start()

            if mqttClient.connected_flag is False:
               logger.warning("Skipping packet processing - no MQTT broker connected")
               continue
            
            updateTime = datetime.datetime.utcnow().replace(tzinfo=datetime.timezone.utc).isoformat()

            url = 'http://%s/current-sample' % (gConf.configOpts['neurioAddress'])
            response = requests.get(url)
            data = response.json()

# From the Neurio local API documentation
#    timestamp: Represents the UTC date/time value when measurement was executed in ISO8601 format. In case of an unsynchronized sensor time, this value is set to NOT_SYNCHRONIZED.
#    channels: Array containing information for [up to] the six logical channels.
#    cts: An array of 4 CTs.
#
# For channels the following applies:
#    type: Channel type in string format. Possible values are: PHASE_A_CONSUMPTION, PHASE_B_CONSUMPTION, PHASE_C_CONSUMPTION, NET, GENERATION, CONSUMPTION, SUBMETER.
#    ch: Channel number
#    eImp_Ws: Imported energy in watt-seconds
#    eExp_Ws: Exported energy in watt-seconds
#    p_W: Real power in watts
#    q_VAR: Reactive power in volt-amps reactive
#    v_V: Voltage in volts
#    label: User defined channel label. Only returned for SUBMETER type channels.
# For cts the following applies:
#    ct: CT enumeration
#    p_W: Real power in watts
#    q_Var: Reactive power in volt-amps reactive
#    v_V: Voltage in volts

            # Things to send up:
            #  Total V, WATTS, VAR
            #  Phase V, I, W, VAR

            channels = { }

            for channel in data['channels']:
               name = channel['type']
               number = channel['ch']
               energy = channel['eImp_Ws']
               p = channel['p_W']
               q = channel['q_VAR']
               v = channel['v_V']
               pf = p / math.sqrt((p**2) + (q**2))
               pf = math.cos(math.atan(q/p))
               if name == 'PHASE_A_CONSUMPTION':
                  name = 'phaseA'
               elif name == 'PHASE_B_CONSUMPTION':
                  name = 'phaseB'
               else:
                  name = None
                  
               if name is not None:
                  channels[name] = {'number':number, 'energy':energy, 'real_power':p, 'reactive_power':q, 'volts':v, 'pf':pf }
               

            sensors = ['phaseA_voltage', 'phaseB_voltage', 'phaseA_power', 'phaseB_power', 'phaseA_pf', 'phaseB_pf', 'voltage', 'power']

            value = "0"
            units = 'unknown'
            topic = ''
            for sensor in sensors:
               if sensor == 'phaseA_voltage':
                  value = "%.1f" % (channels['phaseA']['volts'])
                  units = 'volts'
               elif sensor == 'phaseB_voltage':
                  value = "%.1f" % (channels['phaseB']['volts'])
                  units = 'volts'               
               elif sensor == 'phaseA_power':
                  value = channels['phaseA']['real_power']
                  units = 'watts'
               elif sensor == 'phaseB_power':
                  value = channels['phaseB']['real_power']
                  units = 'watts'
               elif sensor == 'phaseA_pf':
                  value = "%.2f" % (channels['phaseA']['pf'])
                  units = 'none'
               elif sensor == 'phaseB_pf':
                  value = "%.2f" % (channels['phaseB']['pf'])
                  units = 'none'
               elif sensor == 'voltage':
                  value = "%.1f" % (channels['phaseA']['volts'] + channels['phaseB']['volts'])
                  units = 'volts'
               elif sensor == 'power':
                  value = channels['phaseA']['real_power'] + channels['phaseB']['real_power']
                  units = 'watts'            
               else:
                  logging.error("Unknown sensor name [%s]" % (sensor))


               try:
                  topic = "%s/%s/%s" % (gConf.configOpts['locale'], gConf.configOpts['neurioName'], sensor)

                  logging.debug("Publishing [%s] to topic [%s]" % (value, topic))
            
                  updateMessage = {
                     'type':'update',
                     'value':value,
                     'units':units,
                     'time':updateTime,
                     'source':gConf.configOpts['sourceName']
                  }


                  message = json.dumps(updateMessage, sort_keys=True)
                  if mqttClient.connected_flag is True:
                     mqttClient.publish(topic=topic, payload=message)
               except Exception as e:
                  logger.exception("Failed to post update for [%s]" % (topic))
               

            time.sleep(gConf.configOpts['postInterval'])           

         except (KeyboardInterrupt):
            logger.warning("Caught KeyboardInterrupt, terminating")
            raise
         
         except Exception as e:
            logger.exception("Caught some sort of exception, restarting the whole thing")
            exc_info = sys.exc_info()
            traceback.print_exception(*exc_info)
            del exc_info         

   # Highest level, outer interrupt handler.  
   except (KeyboardInterrupt):
      logger.info("User requested program termination, exiting...")
      try:
         if mqttClient is not None and mqttClient.connected_flag is True:
            mqttClient.disconnect()
      except:
         pass
      logger.info("Terminated")
      logging.shutdown()

if __name__ == "__main__":
   ap = argparse.ArgumentParser()
   ap.add_argument("-d", "--daemon", help="Daemon control:  start / stop / restart", type=str, default=None)
   ap.add_argument("-p", "--pidfile", help="Daemon pid file", type=str, default='/tmp/sensorbridge-neurio.pid')
   ap.add_argument("-l", "--logfile", help="Log file", type=str, default=None)
   ap.add_argument("-c", "--config", help="specify file with configuration", type=str, default='sensorbridge-neurio.cfg')
   args = ap.parse_args()
   
   # Because we might become a daemon, we need to canonicalize our path to our configuration file
   pwd = os.getcwd()
   configFileName = os.path.basename(args.config)
   configDir = os.path.dirname(args.config)
   if configDir is None or len(configDir) == 0:
      configDir = pwd
   configFile = "%s/%s" % (configDir, configFileName)
   
   isDaemon = False
   
   if args.daemon is not None:
      pidfile=args.pidfile
      daemonize.startstop(action=args.daemon, stdout='/dev/null', pidfile=pidfile)
      isDaemon = True
      
   mainParms = {'startupDirectory': pwd, 'configFile': configFile, 'isDaemon':isDaemon, 'logFile':args.logfile }
   
   try:
      main(mainParms)
   except Exception as e:
      print(e)
      if args.daemon is not None:
         try:
            os.remove(pidfile)
         except IOError:
            pass
