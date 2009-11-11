#!/usr/bin/python -O
#Remove -O to get debugging output

'''
Version: 1.0                                                                
Created: 2009-10-30                                                      
Author: Erinn Looney-Triggs
Revised:
Revised by: 

License:
    <one line to give the program's name and a brief idea of what it does.>
    Copyright (C) 2009  Erinn Looney-Triggs

    This program is free software: you can redistribute it and/or modify
    it under the terms of the GNU Affero General Public License as
    published by the Free Software Foundation, either version 3 of the
    License, or (at your option) any later version.

    This program is distributed in the hope that it will be useful,
    but WITHOUT ANY WARRANTY; without even the implied warranty of
    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
    GNU Affero General Public License for more details.

    You should have received a copy of the GNU Affero General Public License
    along with this program.  If not, see <http://www.gnu.org/licenses/>.

'''



import sys

__author__ = 'Erinn Looney-Triggs'
__credits__ = ['Erinn Looney-Triggs', ]
__license__ = 'AGPL 3.0'
__maintainer__ = 'Erinn Looney-Triggs'
__email__ = 'erinn.looneytriggs@gmail.com'
__version__ = 1.0
__status__ = 'Development'

#Nagios exit codes in English
UNKNOWN  = 3
CRITICAL = 2
WARNING  = 1
OK       = 0

class Snmp(object):
    '''
    A Basic Class For an SNMP Session
    '''
    def __init__(self,
                version = '2c',
                destHost = 'localhost',
                community = 'public',
                verbose = 0):

        self.community = community
        self.destHost = destHost
        self.verbose = verbose
        self.version = version

    def query(self, snmpCmd, oid):
        '''
        Creates SNMP query session. 
        
        snmpcmd is a required string that can either be 'snmpget' 
        or 'snmpwalk'.
        
        oid is a required string that is the numerical OID to be used.
        '''
        
        import subprocess
        
        fullSnmpCmd = self.__which(snmpCmd)
        
        if not fullSnmpCmd:
            print snmpCmd, ('is not available in your path, or is not '
                            'executable by you, exiting.')
            sys.exit(CRITICAL)
            
        cmdLine = ('{snmpCmd} -v {version} -O vq -c {community} '
                   '{destHost} {oid}')
        
        cmdLine = cmdLine.format(snmpCmd = snmpCmd, version = self.version, 
                                 community = self.community, 
                                 destHost= self.destHost, oid = oid)
        
        if self.verbose:
            print 'Performing SNMP query:', cmdLine
        
        try:
            p = subprocess.Popen(cmdLine, shell=True, 
                                 stdout = subprocess.PIPE, 
                                 stderr = subprocess.STDOUT)
        except OSError:
            print 'Error:', sys.exc_value, 'exiting!'
            sys.exit(WARNING) 
        
        #This is where we sanitize the output gathered.
        output = p.stdout.read().strip()
        
        if snmpCmd == 'snmpwalk':
            output = output.split()
        
        return output
    
    def __which(self, program):
        '''This is the equivalent of the 'which' BASH built-in with a 
        check to make sure the program that is found is executable.
        '''
        
        import os
        
        def is_exe(file_path):
            '''Tests that a file exists and is executable.
            '''
            return os.path.exists(file_path) and os.access(file_path, os.X_OK)
        
        file_path, fname = os.path.split(program)
        
        if file_path:
            if is_exe(program):
                return program
        else:
            for path in os.environ["PATH"].split(os.pathsep):
                exe_file = os.path.join(path, program)
                if is_exe(exe_file):
                    return exe_file
    
        return None

class CheckInfortrend(Snmp):
    '''
    Main class that performs checks against the passed in RAID, this class 
    inherits from Snmp so Snmp is required or a suitable substitute needs
    to be made.
    
    There are four optional arguments that are passed to the init constructor:
    community: a string giving the community password
    desthost: a string giving the destination host as either an IP for FQDN
    verbose: a integer, any number other than zero will give you verbose output
    version: a string specifying the SNMP version to use only 1, and 2c are
    supported
    '''
    
    def __init__(self, community = 'public', destHost = 'localhost', 
                 verbose = 0, version = '2c'):
        
        self.baseoid = ''           #Base OID found during auto detect
        self.community = community
        self.destHost = destHost
        
        # Holder for state counts
        self.state = {'critical' : 0, 'unknown': 0, 'warning' : 0}
        
        # Holder for nagios output and perfdata output
        self.output = []
        self.perfData = []
        
        self.verbose = verbose
        self.version = version
        
        # Initialize our superclass
        Snmp.__init__(self, self.version, self.destHost, self.community, 
                      self.verbose)
        
    def autoDetect(self):
        '''
        Perform auto detection on designated SNMP agent in order 
        to determine which base OID to use.
        
        There can be more OIDs, and I am sure there are. Just add the base OID
        to the list and the agent can be detected.
        
        This method expects no arguments.
        '''
        
        #Infortrend's base oid: 1.3.6.1.4.1.1714.
        #Sun's base oid for 3510: 1.3.6.1.4.1.42.2.180.3510.1.
        #Sun's base oid for 3511: 1.3.6.1.4.1.42.2.180.3511.1.
        
        baseoids = ['1.3.6.1.4.1.1714.', '1.3.6.1.4.1.42.2.180.3510.1.', 
                    '1.3.6.1.4.1.42.2.180.3510.1.',]
        
        for baseoid in baseoids:
            result = self.query('snmpget', baseoid + '1.1.1.10')
            
            if result != 'No Such Object available on this agent at this OID':
                self.baseoid = baseoid
                break
        
        if not self.baseoid:
            print 'Unable to auto detect array type, exiting.'
            sys.exit(CRITICAL)
        
        if self.verbose:
            print 'Base OID set to:', self.baseoid
        
        return
       
    def check(self):
        '''
        Convenience method that will run all of the checks against the 
        RAID.
        
        This method expects no arguments.
        '''
        
        self.autoDetect()
        self.checkModelFirmware()
        self.checkDriveStatus()
        self.checkDeviceStatus()
        self.parsePrint()
        
    def __checkHddStatus(self, hdds):
        '''
        For internal use, parses list returned from hddStatus OID and checks
        for error conditions. Requires one argument hdds which has to be a 
        list of one or more return values from hddStatus OID.
        '''
        
        # For completeness here are the other codes that we accept as being
        # good.
        # 1 : On-Line Drive
        # 2 : Used Drive
        # 3 : Spare Drive
        # 9 : Global Spare Drive
        # 18 : Drive is a valid Clone of another Drive
        # 128 to 143 : SCSI Device
        
        warningCodes  = {0:'New (Unassigned) Drive', 
                         4:'Drive Initialization in Progress', 
                         5:'Drive Rebuild in Progress', 
                         6:'Add Drive to Logical Drive in Progress', 
                         17:'Drive is in process of Cloning another Drive', 
                         19:'Drive is in process of Copying from another Drive'
                         }
        
        criticalCodes = {63:'Drive Absent', 
                         252:'Missing Global Spare Drive', 
                         253:'Missing Spare Drive', 
                         254:'Missing Drive',
                         255:'Failed Drive'
                         }
        
        
        
        if __debug__:
            print 'Debug: Warning codes dictionary:', warningCodes
            print 'Debug: Critical codes dictionary:', criticalCodes
            print 'Debug: List of hdds to check:', hdds
        
        for drive, status in enumerate(hdds):
            if __debug__:
                print 'Debug: checking drive:', drive, 'with status:', status
            
            status = int(status)
            
            if status in criticalCodes:
                self.state['critical'] += 1
                self.output.append('Drive ' + str(drive + 1) + ': ' 
                                + criticalCodes[status])
                
            elif status in warningCodes:
                self.state['warning'] += 1
                self.output.append('Drive ' + str(drive + 1) + ': ' 
                                + warningCodes[status])
                
        
        if __debug__:
            print ('Debug: Results gathered before exiting __checkHddStatus:'
                   '{0} {1}').format(self.state, self.output)
            
        return
    
    def __checkLdStatus(self, logicalDrives):
        '''
        For internal use. Check the status of the logical drives, expects 
        a list of strings gathered from the ldStatus OID.
        '''

        warningCodes = {1:'Rebuilding', 
                        2:'Initializing', 
                        3:'Degraded',
                        }
        
        criticalCodes = {4:'Dead', 
                         5:'Invalid', 
                         6:'Incomplete', 
                         7:'Drive Missing',
                         64:'Logical Drive Off-line'
                         }
        
        for drive, status in enumerate(logicalDrives):
            if __debug__:
                print ('Debug: Checking logical drive: '
                       '{0} with status: {1}').format(drive, status)
             
            status = int(status)
            

            if status in criticalCodes:
                self.state['critical'] += 1
                self.output.append('Logical Drive ' + str(drive + 1) + ': ' 
                            + criticalCodes[int(status)])
                
            elif int(status) in warningCodes:
                self.state['warning'] += 1
                self.output.append('Drive ' + str(drive + 1) + ': ' 
                                + warningCodes[int(status)])      
        
        return None
    

    def checkDeviceStatus(self):
        '''
        Check the status of the RAID device and most associated components.
        This checks components like the CPU temperature, fan speed, sensor 
        temperatures, etc.
        
        This method expects no arguments.
        
        OIDs we want:
        Logical Unit Status       1.3.6.1.4.1.1714.1.9.1.13
        '''
        
#         ('Logical Unit Index:', '1.3.6.1.4.1.1714.1.9.1', 'snmpwalk'),
        # OIDs of interest here 
        pass
    
    def checkDriveStatus(self):
        '''
        Check the Hard Drive Status of the RAID and return the result.
        
        This method expects no arguments.
        
        This will check:
        Logical Disk Drive Count
        Logical Disk Spare Drive Count
        Logical Disk Failed Drive Count
        Logical Disk Status and parse the results for any error conditions
        Hard Drive Status and parse the results for any error conditions
        '''     
        
        ldTotalDrvCnt = ('Logical Drives:', self.baseoid + '1.2.1.8', 
                         'snmpwalk')
        ldSpareDrvCnt = ('Spare Drives:', self.baseoid + '1.2.1.10',
                 'snmpwalk')
        ldFailedDrvCnt = ('Failed Drives:', self.baseoid + '1.2.1.11', 
                          'snmpwalk')
        ldStatus = ('Logical Drive Status:', self.baseoid + '1.2.1.6',
                     'snmpwalk')
        hddStatus = ('Hard Drive Status:', self.baseoid + '1.6.1.11',
                      'snmpwalk')
        
        #TODO: Clearly there is some redundancy here
        # Get the logical drive count
        check, oid, snmpCmd = ldTotalDrvCnt
        driveCount = ','.join(self.query(snmpCmd, oid))
        
        if self.verbose:
            print check, driveCount
            
        self.output.append(check + driveCount)
        
        # Get the spare drive count
        check, oid, snmpCmd = ldSpareDrvCnt
        spareCount = ','.join(self.query(snmpCmd, oid))
        
        if self.verbose:
            print check, spareCount
            
        self.output.append(check + spareCount)
        
        # Get the failed drive count
        check, oid, snmpCmd = ldFailedDrvCnt
        failedCount = ','.join(self.query(snmpCmd, oid))
        
        if self.verbose:
            print check, failedCount
            
        self.output.append(check + failedCount)
        
        # Get the logical disk status
        check, oid, snmpCmd = ldStatus
        logicalDriveStatus = self.query(snmpCmd, oid)
        
        if self.verbose:
            print check , logicalDriveStatus
        
        self.__checkLdStatus(logicalDriveStatus)
        
        #Get the status of the hard drives
        check, oid, snmpCmd = hddStatus
        driveStatus =  self.query(snmpCmd, oid)
        
        if self.verbose:
            print check , driveStatus
        
        self.__checkHddStatus(driveStatus)
        
        return
    
    def checkModelFirmware(self):
        '''
        Pull the system's make, model, serial number, firmware major and minor 
        numbers. Expects no arguments to be passed in.
        
        This method expects no arguments.
        '''
        
        privateLogoVendor = ('Vendor:',self.baseoid + '1.1.1.14.0', 'snmpget')
        privateLogoString = ('Model:', self.baseoid + '1.1.1.13.0', 'snmpget')
        serialNum = ('Serial Number:', self.baseoid + '1.1.1.10.0', 'snmpget')
        fwMajorVersion = ('Firmware Major Version:', 
                          self.baseoid + '1.1.1.4.0', 'snmpget')
        fwMinorVersion = ('Firmware Minor Version:', 
                          self.baseoid + '1.1.1.5.0', 'snmpget')
        
        # Get the vendor string
        check, oid, snmpCmd = privateLogoVendor
        vendor = self.query(snmpCmd, oid)
        if self.verbose:
            print check, vendor
            
        self.output.append(check + vendor)
        
        # Get the Manufacturers model
        check, oid, snmpCmd = privateLogoString
        model = self.query(snmpCmd, oid)
        if self.verbose:
            print check, model
            
        self.output.append(check + model)
        
        # Get the serial number
        check, oid, snmpCmd = serialNum
        serialNumber = self.query(snmpCmd, oid)
        if self.verbose:
            print check, serialNumber
            
        self.output.append(check + serialNumber)
        
        # Get the major and minor firmware versions
        check, oid, snmpCmd = fwMajorVersion
        firmwareMajor = self.query(snmpCmd, oid)
        if self.verbose:
            print check, firmwareMajor
        
        check, oid, snmpCmd = fwMinorVersion
        firmwareMinor = self.query(snmpCmd, oid)
        if self.verbose:
            print check, firmwareMinor
        
        self.output.append('Firmware Version:' + firmwareMajor 
                   + '.' + firmwareMinor)
        
        if __debug__:
            print 'Debug: Output from checkModelFirmware:', self.output
        
        return
    
    def parsePrint(self):
        '''
        Parse the results
        '''
        
        finalOutput = '{status}:{output}'
        
        if __debug__:
            print ('Debug: Results passed to parsePrint: '
                   '{0} {1}').format(self.state, self.output)
            
        
        if self.state['critical']:
            status = 'CRITICAL'
        elif self.state['warning']:
            status = 'WARNING'
        elif self.state['unknown']:
            status = 'UNKNOWN'
        else:
            status = 'OK'
        
        finalLine = ''
        
        for line in self.output:
            finalLine += ' ' + line + ' ' 
        
        # Add in performance data if it exists
        if self.perfData:
            finalLine += '|'
            for line in self.perfData:
                finalLine += line
        
        #Construct and print our final output
        finalOutput = finalOutput.format(status = status, output = finalLine)
        print finalOutput
        
        if self.state['critical']:
            sys.exit(CRITICAL)
        elif self.state['warning']:
            sys.exit(WARNING)
        elif self.state['unknown']:
            sys.exit(UNKNOWN)
        else:
            sys.exit(OK)
        
        return None #Should never be reached
    

def sigalarm_handler(signum, frame):
    '''Handler for an alarm situation.'''
    
    print '{0} timed out after {1} seconds'.format(sys.argv[0], 
                                                   options.timeout)
    sys.exit(CRITICAL)
    
if __name__ == '__main__':
    import optparse
    import signal
    
    RESULTS = []

    
    parser = optparse.OptionParser(description='''Nagios plug-in to monitor
    Infortrend based RAIDs, this includes some Sun StorEdge RAIDs such 
    as the 3510 and the 3511.''', prog="check_infortrend", 
    version="%prog Version: 1.0")
    
    parser.add_option('-c', '--community', action='store', 
                      dest='community', type='string',default='public', 
                      help=('SNMP Community String to use. '
                      '(Default: %default)'))
    parser.add_option('-H', '--hostname', action='store', type='string', 
                      dest='hostname', default='localhost',
                      help='Specify hostname for SNMP (Default: %default)')
    parser.add_option('-t', '--timeout', dest='timeout', default=10,
                      help=('Set the timeout for the program to run '
                      '(Default: %default seconds)'), type='int', 
                      metavar='<ARG>')
    parser.add_option('-v', '--verbose', action='count', dest='verbose', 
                      default=0, help=('Give verbose output,'
                      '(Default: Off)') )
    
    (options, args) = parser.parse_args()
    
    if __debug__:
        print 'Options taken in:', options
        print 'Arguments taken in:', args
        
    signal.signal(signal.SIGALRM, sigalarm_handler)
    
    signal.alarm(options.timeout)
    
    #Instantiate our object
    c = CheckInfortrend(community = options.community, 
                        destHost = options.hostname, 
                        verbose = options.verbose)
    
    
    #This runs all of the checks
    c.check()
    
    signal.alarm(0)

        