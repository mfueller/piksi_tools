#!/usr/bin/env python
# Copyright (C) 2011-2015 Swift Navigation Inc.
# Contact: Fergus Noble <fergus@swift-nav.com>
#
# This source is subject to the license found in the file 'LICENSE' which must
# be be distributed together with this source. All other rights reserved.
#
# THIS CODE AND INFORMATION IS PROVIDED "AS IS" WITHOUT WARRANTY OF ANY KIND,
# EITHER EXPRESSED OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE IMPLIED
# WARRANTIES OF MERCHANTABILITY AND/OR FITNESS FOR A PARTICULAR PURPOSE.

"""
The :mod:`piksi_tools.serial_link` module contains functions related to
setting up and running SBP message handling.
"""

import sys
import os
import time
import uuid
import warnings

from sbp.bootload                       import *
from sbp.logging                        import *
from sbp.piksi                          import MsgReset
from sbp.client.drivers.network_drivers import HTTPDriver
from sbp.client.drivers.pyserial_driver import PySerialDriver
from sbp.client.drivers.pyftdi_driver   import PyFTDIDriver
from sbp.client.drivers.cdc_driver      import CdcDriver
from sbp.client.loggers.json_logger     import JSONLogger
from sbp.client.loggers.null_logger     import NullLogger
from sbp.client                         import Handler, Framer, Forwarder
import serial.tools.list_ports

from piksi_tools.utils import mkdir_p

SERIAL_PORT  = "/dev/ttyUSB0"
SERIAL_BAUD  = 115200
CHANNEL_UUID = '118db405-b5de-4a05-87b5-605cc85af924'
DEFAULT_BASE = "http://broker.staging.skylark.swiftnav.com"

def logfilename():
  return time.strftime("serial-link-%Y%m%d-%H%M%S.log.json") 

def get_ports():
  """
  Get list of serial ports.
  """
  return [p for p in serial.tools.list_ports.comports() if p[1][0:4] != "ttyS"]

def base_cl_options(override_arg_parse=None, add_help=True):
  import argparse
  if override_arg_parse:
    parserclass = override_arg_parse
  else:
    parserclass = argparse.ArgumentParser
  parser = parserclass(description="Swift Navigation SBP Client.", add_help=add_help)
  parser.add_argument("-p", "--port",
                      default=None,
                      help="specify the serial port to use.")
  parser.add_argument("-b", "--baud",
                      default=SERIAL_BAUD,
                      help="specify the baud rate to use.")
  parser.add_argument("-v", "--verbose",
                      action="store_true",
                      help="print extra debugging information.")
  parser.add_argument("-f", "--ftdi",
                      action="store_true",
                      help="use pylibftdi instead of pyserial.")
  parser.add_argument("-l", "--log",
                      action="store_true",
                      help="serialize SBP messages to autogenerated log file.")
  parser.add_argument("-r", "--reset",
                      action="store_true",
                      help="reset device after connection.")
  parser.add_argument("-o", "--log-dirname",
                      default='',
                      help="directory in which to create logfile.")
  parser.add_argument("--logfilename", default='',
                      help='filename to use for log. Default filename with date and timestamp is used otherwise.')
  parser.add_argument("-a", "--append-log-filename",
                      default=None,
                      help="file to append log output to.")
  parser.add_argument("--file",
                      help="Read with a filedriver rather than pyserial.",
                      action="store_true")
  parser.add_argument("-d", "--tags",
                      default=None,
                      help="tags to decorate logs with.")
  parser.add_argument("-t", "--tcp", action="store_true", default=False,
                      help="Use a TCP connection instead of a local serial port. \
                      If TCP is selected, the port is interpreted as host:port")
  return parser

def get_args():
  """
  Get and parse arguments.
  """
  import argparse
  parser = base_cl_options()
  parser.add_argument("-u", "--base", default=DEFAULT_BASE,
                      help="Base station URI.")
  parser.add_argument("-c", "--channel_id",
                      default=CHANNEL_UUID,
                      help="Networking channel ID.")
  parser.add_argument("-s", "--serial_id",
                      default=None,
                      help="Device ID.")
  parser.add_argument("-x", "--broker",
                      action="store_true",
                      help="Used brokered SBP data.")
  parser.add_argument("--timeout",
                      default=None,
                      help="exit after TIMEOUT seconds have elapsed.")
  return parser.parse_args()

def get_driver(use_ftdi=False, port=SERIAL_PORT, baud=SERIAL_BAUD, file=False):
  """
  Get a driver based on configuration options

  Parameters
  ----------
  use_ftdi : bool
    For serial driver, use the pyftdi driver, otherwise use the pyserial driver.
  port : string
    Serial port to read.
  baud : int
    Serial port baud rate to set.
  """
  try:
    if use_ftdi:
      return PyFTDIDriver(baud)
    if file:
      return open(port, 'rb')
  # HACK - if we are on OSX and the device appears to be a CDC device, open as a binary file
    for each in serial.tools.list_ports.comports():
      if port == each[0]:
        if each[1].startswith("Gadget Serial"):
          print("opening a file driver")
          return CdcDriver(open(port, 'w+b', 0 ))
    return PySerialDriver(port, baud)
  # if finding the driver fails we should exit with a return code
  # currently sbp's py serial driver raises SystemExit, so we trap it
  # here
  except SystemExit:
    sys.exit(1)

def get_logger(use_log=False, filename=logfilename()):
  """
  Get a logger based on configuration options.

  Parameters
  ----------
  use_log : bool
    Whether to log or not.
  filename : string
    File to log to.
  """
  if not use_log:
    return NullLogger()
  dirname = os.path.dirname(filename)
  if dirname:
   mkdir_p(dirname) 
  print("Starting JSON logging at %s" % filename)
  infile = open(filename, 'w')
  return JSONLogger(infile)

def get_append_logger(filename, tags):
  """
  Get a append logger based on configuration options.

  Parameters
  ----------
  filename : string
    File to log to.
  tags : string
    Tags to log out
  """
  if not filename:
    return NullLogger()
  print("Append logging at %s" % filename)
  infile = open(filename, 'a')
  return JSONLogger(infile, tags)

def printer(sbp_msg, **metadata):
  """
  Default print callback

  Parameters
  ----------
  sbp_msg: SBP
    SBP Message to print out.
  """
  print(sbp_msg.payload, end=' ')

def log_printer(sbp_msg, **metadata):
  """
  Default log callback

  Parameters
  ----------
  sbp_msg: SBP
    SBP Message to print out.
  """
  levels = {0: 'EMERG',
            1: 'ALERT',
            2: 'CRIT',
            3: 'ERROR',
            4: 'WARN',
            5: 'NOTICE',
            6: 'INFO',
            7: 'DEBUG'}
  m = MsgLog(sbp_msg)
  print(levels[m.level], m.text)

def swriter(link):
  """Callback intended for reading out messages from one stream and into
  a serial link stream.

  Parameters
  ----------
  link : file handle

  Returns
  ----------
  A callback function taking an SBP message.

  """
  def scallback(sbp_msg, **metadata):
    link(sbp_msg)
  return scallback

def get_uuid(channel, serial_id):
  """Returns a namespaced UUID based on the piksi serial number and a
  namespace.

  Parameters
  ----------
  channel : str
    UUID namespace
  serial_id : int
    Piksi unique serial number

  Returns
  ----------
  UUID4 string, or None on invalid input.

  """
  if isinstance(channel, str) and isinstance(serial_id, int) and serial_id > 0:
    return uuid.uuid5(uuid.UUID(channel), str(serial_id))
  elif isinstance(channel, str) and isinstance(serial_id, int) and serial_id < 0:
    return uuid.uuid5(uuid.UUID(channel), str(-serial_id))
  else:
    return None

def run(args, link):
  """Spin loop for reading from the serial link.

  Parameters
  ----------
  args : object
    Argparse result.
  link : Handler
    Piksi serial handle

  """
  timeout = args.timeout
  if args.reset:
    link(MsgReset(flags=0))
  try:
    if args.timeout is not None:
      expire = time.time() + float(args.timeout)
    while True:
      if timeout is None or time.time() < expire:
      # Wait forever until the user presses Ctrl-C
        time.sleep(1)
      else:
        print("Timer expired!")
        break
      if not link.is_alive():
        sys.stderr.write("ERROR: Thread died!")
        sys.exit(1)
  except KeyboardInterrupt:
    # Callbacks call thread.interrupt_main(), which throw a
    # KeyboardInterrupt exception. To get the proper error
    # condition, return exit code of 1. Note that the finally
    # block does get caught since exit itself throws a
    # SystemExit exception.
    sys.exit(1)

def main(args):
  """
  Get configuration, get driver, get logger, and build handler and start it.
  """
  port = args.port
  baud = args.baud
  timeout = args.timeout
  log_filename = args.logfilename
  log_dirname = args.log_dirname
  if not log_filename:
    log_filename=logfilename()
  if log_dirname:
    log_filename = os.path.join(log_dirname, log_filename)
  append_log_filename = args.append_log_filename
  tags = args.tags
  # State for handling a networked base stations.
  channel = args.channel_id
  serial_id = int(args.serial_id) if args.serial_id is not None else None
  base = args.base
  use_broker = args.broker
  # Driver with context
  if args.tcp:
    try:
      host, port = port.split(':')
      driver = TCPDriver(host, int(port))
    except:
      raise Exception('Invalid host and/or port')
  else:
    driver = get_driver(args.ftdi, port, baud, args.file)
    # Handler with context
  with Handler(Framer(driver.read, driver.write, args.verbose)) as link:
    # Logger with context
    with get_logger(args.log, log_filename) as logger:
      with get_append_logger(append_log_filename, tags) as append_logger:
        link.add_callback(printer, SBP_MSG_PRINT_DEP)
        link.add_callback(log_printer, SBP_MSG_LOG)
        Forwarder(link, logger).start()
        Forwarder(link, append_logger).start()
        if use_broker and base and serial_id:
          device_id = get_uuid(channel, serial_id)
          with HTTPDriver(str(device_id), base) as http:
            with Handler(Framer(http.read, http.write, args.verbose)) as slink:
              Forwarder(slink, swriter(link)).start()
              run(args, link)
        else:
          run(args, link)

if __name__ == "__main__":
  main(get_args())
