"""

Python Interchangeable Virtual Instrument Library

Copyright (c) 2012-2016 Alex Forencich

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in
all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
THE SOFTWARE.

"""

# import libraries
import inspect
import numpy as np
import re
import abc
from functools import partial

# try importing drivers
# python-vxi11 for LAN instruments
try:
    import vxi11
except ImportError:
    pass

# python-usbtmc for USBTMC instrument support
try:
    import usbtmc
except ImportError:
    pass

# linuxgpib wrapper for linux-gpib Gpib class
# for GPIB interfaces
try:
    from .interface import linuxgpib
except ImportError:
    pass

# pySerial wrapper for serial instrument support
try:
    from .interface import pyserial
except ImportError:
    pass

# pyvisa wrapper for PyVISA library support
try:
    from .interface import pyvisa
except ImportError:
    pass

# set to True to try loading PyVISA first before
# other interface libraries
_prefer_pyvisa = False


def get_prefer_pyvisa():
    global _prefer_pyvisa
    return _prefer_pyvisa


def set_prefer_pyvisa(value=True):
    global _prefer_pyvisa
    _prefer_pyvisa = bool(value)


# version information
from .version import __version__

version = __version__


# Exceptions
class IviException(Exception):
    pass


class IviDriverException(IviException):
    pass


class FileFormatException(IviDriverException):
    pass


class IdQueryFailedException(IviDriverException):
    pass


class InstrumentStatusExcpetion(IviDriverException):
    pass


class InvalidOptionValueException(IviDriverException):
    pass


class IOException(IviDriverException):
    pass


class IOTimeoutException(IviDriverException):
    pass


class MaxTimeoutExceededException(IviDriverException):
    pass


class NotInitializedException(IviDriverException):
    pass


class OperationNotSupportedException(IviDriverException):
    pass


class OperationPendingException(IviDriverException):
    pass


class OptionMissingException(IviDriverException):
    pass


class OptionStringFormatException(IviDriverException):
    pass


class OutOfRangeException(IviDriverException):
    pass


class ResetFailedException(IviDriverException):
    pass


class ResetNotSupportedException(IviDriverException):
    pass


class SelectorFormatException(IviDriverException):
    pass


class SelectorHierarchyException(IviDriverException):
    pass


class SelectorNameException(IviDriverException):
    pass


class SelectorNameRequiredException(IviDriverException):
    pass


class SelectorRangeException(IviDriverException):
    pass


class SimulationStateException(IviDriverException):
    pass


class TriggerNotSoftwareException(IviDriverException):
    pass


class UnexpectedResponseException(IviDriverException):
    pass


class UnknownOptionException(IviDriverException):
    pass


class UnknownPhysicalNameException(IviDriverException):
    pass


class ValueNotSupportedException(IviDriverException):
    pass


def get_index(l, i):
    """Validate index from list or dict of possible values"""
    if type(l) is dict:
        try:
            return l[i]
        except KeyError:
            if type(i) is int:
                raise SelectorRangeException()
            raise SelectorNameException()

    if i in l:
        return l.index(i)
    if type(i) == int:
        if i < 0 or i >= len(l):
            raise SelectorRangeException()
        return i
    raise SelectorNameException()


def get_index_dict(l):
    """Construct a dict object for faster index lookups"""
    d = {}
    for i in range(len(l)):
        d[l[i]] = i
        d[i] = i
    return d


class TraceY(object):
    "Y trace object"

    def __init__(self):
        self.average_count = 1
        self.y_increment = 0
        self.y_origin = 0
        self.y_reference = 0
        self.y_raw = None
        self.y_hole = None

    @property
    def y(self):
        y = np.array(self.y_raw)
        yf = y.astype(float)
        if self.y_hole is not None:
            yf[y == self.y_hole] = float('nan')
        return ((yf - self.y_reference) * self.y_increment) + self.y_origin

    def __getitem__(self, index):
        y = self.y_raw[index]
        if y == self.y_hole:
            y = float('nan')
        return ((y - self.y_reference) * self.y_increment) + self.y_origin

    def __iter__(self):
        return (float('nan') if y == self.y_hole else ((y - self.y_reference) * self.y_increment + self.y_origin) for
                i, y in enumerate(self.y_raw))

    def __len__(self):
        return len(self.y_raw)

    def count(self):
        return len(self.y_raw)


class TraceYT(TraceY):
    "Y-T trace object"

    def __init__(self):
        super(TraceYT, self).__init__()
        self.x_increment = 0
        self.x_origin = 0
        self.x_reference = 0

    @property
    def x(self):
        return ((np.arange(len(self.y_raw)) - self.x_reference) * self.x_increment) + self.x_origin

    @property
    def t(self):
        return self.x

    def __getitem__(self, index):
        y = self.y_raw[index]
        if y == self.y_hole:
            y = float('nan')
        return (((index - self.x_reference) * self.x_increment) + self.x_origin,
                ((y - self.y_reference) * self.y_increment) + self.y_origin)

    def __iter__(self):
        return ((((i - self.x_reference) * self.x_increment) + self.x_origin,
                 float('nan') if y == self.y_hole else ((y - self.y_reference) * self.y_increment) + self.y_origin) for
                i, y in enumerate(self.y_raw))


def build_ieee_block(data):
    "Build IEEE block"
    # IEEE block binary data is prefixed with #lnnnnnnnn
    # where l is length of n and n is the
    # length of the data
    # ex: #800002000 prefixes 2000 data bytes
    return str('#8%08d' % len(data)).encode('utf-8') + data


def decode_ieee_block(data):
    "Decode IEEE block"
    # IEEE block binary data is prefixed with #lnnnnnnnn
    # where l is length of n and n is the
    # length of the data
    # ex: #800002000 prefixes 2000 data bytes
    if len(data) == 0:
        return b''

    ind = 0
    c = '#'.encode('utf-8')
    while data[ind:ind + 1] != c:
        ind += 1

    ind += 1
    l = int(data[ind:ind + 1])
    ind += 1

    if (l > 0):
        num = int(data[ind:ind + l].decode('utf-8'))
        ind += l

        return data[ind:ind + num]
    else:
        return data[ind:]


def get_sig(sig):
    "Parse various signal inputs into x and y components"
    if type(sig) == tuple and len(sig) == 2:
        # tuple of two lists or arrays
        x, y = sig
        x = np.array(x)
        y = np.array(y)
    elif type(sig) == list and type(sig[0]) == tuple and len(sig[0]) == 2:
        # list of tuples
        x, y = zip(*sig)
        x = np.array(x)
        y = np.array(y)
    elif (type(sig) == np.ndarray or type(sig) == np.matrix) and len(sig.shape) == 2 and sig.shape[0] == 2:
        # 2D array, hieght 2
        x = np.array(sig[0])
        y = np.array(sig[1])
    elif (type(sig) == np.ndarray or type(sig) == np.matrix) and len(sig.shape) == 2 and sig.shape[1] == 2:
        # 2D array, width 2
        x = np.array(sig[:, 0])
        y = np.array(sig[:, 1])
    else:
        raise Exception('Unknown argument')

    if len(x) != len(y):
        raise Exception('Signals must be the same length!')

    return x, y


def rms(y):
    "Calculate the RMS value of the signal"
    return np.linalg.norm(y) / np.sqrt(y.size)


def add_group_capability(obj, cap):
    obj.__dict__.setdefault('_identity_group_capabilities', list())
    obj._identity_group_capabilities.insert(0, cap)


class DriverOperation(abc.ABC):
    "Inherent IVI methods for driver operation"

    def __init__(self, *args, **kwargs):
        super(DriverOperation, self).__init__()

        self._driver_operation_cache = True
        self._driver_operation_driver_setup = ""
        self._driver_operation_interchange_check = False
        self._driver_operation_logical_name = ""
        self._driver_operation_query_instrument_status = False
        self._driver_operation_range_check = True
        self._driver_operation_record_coercions = False
        self._driver_operation_io_resource_descriptor = ""
        self._driver_operation_simulate = False

        self._driver_operation_interchange_warnings = list()
        self._driver_operation_coercion_records = list()

    @property
    def operation_cache(self):
        """
        If True, the specific driver caches the value of attributes, and the IVI
        specific driver keeps track of the current instrument settings so that it
        can avoid sending redundant commands to the instrument. If False, the
        specific driver does not cache the value of attributes.

        The default value is True. When the user opens an instrument session
        through an IVI class driver or uses a logical name to initialize a
        specific driver, the user can override this value by specifying a value in
        the IVI configuration store. The Initialize function allows the user to
        override both the default value and the value that the user specifies in
        the IVI configuration store.
        """
        return self._driver_operation_cache

    @operation_cache.setter
    def operation_cache(self, value):
        self._driver_operation_cache = bool(value)

    @property
    def driver_setup(self):
        """
        Returns the driver setup string that the user specified in the IVI
        configuration store when the instrument driver session was initialized or
        passes in the OptionString parameter of the Initialize function. Refer to
        Section 6.14, Initialize, for the restrictions on the format of the driver
        setup string.

        The string that this attribute returns does not have a predefined maximum
        length.
        """
        return self._driver_operation_driver_setup

    @property
    def interchange_check(self):
        """
        If True, the specific driver performs interchangeability checking. If the
        Interchange Check attribute is enabled, the specific driver maintains a
        record of each interchangeability warning that it encounters. The user
        calls the Get Next Interchange Warning function to extract and delete the
        oldest interchangeability warning from the list. Refer to Section 6.11,
        Get Next Interchange Warning, Section 6.2, Clear Interchange Warnings,
        and Section 6.18, Reset Interchange Check, for more information. If False,
        the specific driver does not perform interchangeability checking.

        If the user opens an instrument session through an IVI class driver and
        the Interchange Check attribute is enabled, the IVI class driver may
        perform additional interchangeability checking. The IVI class driver
        maintains a list of the interchangeability warnings that it encounters.
        The user can retrieve both class driver interchangeability warnings and
        specific driver interchangeability warnings by calling the Get Next
        Interchange Warning function on the class driver session.

        If the IVI specific driver does not implement interchangeability checking,
        the specific driver returns the Value Not Supported error when the user
        attempts to set the Interchange Check attribute to True. If the specific
        driver does implement interchangeability checking and the user opens an
        instrument session through an IVI class driver, the IVI class driver
        accepts True as a valid value for the Interchange Check attribute even if
        the class driver does not implement interchangeability checking
        capabilities of its own.

        The default value is False. If the user opens an instrument session
        through an IVI class driver or initializes an IVI specific driver with a
        logical name, the user can override this value in the IVI configuration
        store. The Initialize function allows the user to override both the
        default value and the value that the userspecifies in the IVI
        configuration store.
        """
        return self._driver_operation_interchange_check

    @interchange_check.setter
    def interchange_check(self, value):
        self._driver_operation_interchange_check = bool(value)

    @property
    def logical_name(self):
        """
        Returns the IVI logical name that the user passed to the Initialize
        function. If the user initialized the IVI specific driver directly and did
        not pass a logical name, then this attribute returns an empty string.
        Refer to IVI-3.5: Configuration Server Specification for restrictions on
        the format of IVI logical names.

        The string that this attribute returns contains a maximum of 256
        characters including the NULL character.
        """
        return self._driver_operation_logical_name

    @property
    def query_instrument_status(self):
        """
        If True, the IVI specific driver queries the instrument status at the end
        of each user operation. If False, the IVI specific driver does not query
        the instrument status at the end of each user operation. Querying the
        instrument status is very useful for debugging. After validating the
        program, the user can set this attribute to False to disable status
        checking and maximize performance. The user specifies this value for the
        entire IVI driver session.

        The default value is False. When the user opens an instrument session
        through an IVI class driver or uses a logical name to initialize an IVI
        specific driver, the user can override this value by specifying a value in
        the IVI configuration store. The Initialize function allows the user to
        override both the default value and the value that the user specifies in
        the IVI configuration store.
        """
        return self._driver_operation_query_instrument_status

    @query_instrument_status.setter
    def _set_driver_operation_query_instrument_status(self, value):
        self._driver_operation_query_instrument_status = bool(value)

    @property
    def range_check(self):
        """
        If True, the IVI specific driver validates attribute values and function
        parameters. If False, the IVI specific driver does not validate attribute
        values and function parameters.

        If range check is enabled, the specific driver validates the parameter
        values that users pass to driver functions. Validating attribute values
        and function parameters is useful for debugging. After validating the
        program, the user can set this attribute to False to disable range
        checking and maximize performance. The default value is True. When the
        user opens an instrument session through an IVI class driver or uses a
        logical name to initialize an IVI specific driver, the user can override
        this value by specifying a value in the IVI configuration store. The
        Initialize function allows the user to override both the default value and
        the value that the user specifies in the IVI configuration store.
        """
        return self._driver_operation_range_check

    @range_check.setter
    def range_check(self, value):
        self._driver_operation_range_check = bool(value)

    @property
    def record_coercions(self):
        """
        If True, the IVI specific driver keeps a list of the value coercions it
        makes for ViInt32 and ViReal64 attributes. If False, the IVI specific
        driver does not keep a list of the value coercions it makes for ViInt32 and
        ViReal64 attributes.

        If the Record Value Coercions attribute is enabled, the specific driver
        maintains a record of each coercion. The user calls the Get Next Coercion
        Record function to extract and delete the oldest coercion record from the
        list. Refer to Section 6.10, Get Next Coercion Record, for more
        information.

        If the IVI specific driver does not implement coercion recording, the
        specific driver returns the Value Not Supported error when the user
        attempts to set the Record Value Coercions attribute to True.

        The default value is False. When the user opens an instrument session
        through an IVI class driver or uses a logical name to initialize a IVI
        specific driver, the user can override this value by specifying a value in
        the IVI configuration store. The Initialize function allows the user to
        override both the default value and the value that the user specifies in
        the IVI configuration store.
        """
        return self._driver_operation_record_coercions

    @record_coercions.setter
    def record_coercions(self, value):
        self._driver_operation_record_coercions = bool(value)

    def io_resource_descriptor(self):
        """
        Returns the resource descriptor that the user specified for the physical
        device. The user specifies the resource descriptor by editing the IVI
        configuration store or by passing a resource descriptor to the Initialize
        function of the specific driver. Refer to Section 6.14, Initialize, for the
        restrictions on the contents of the resource descriptor string.

        The string that this attribute returns contains a maximum of 256 characters
        including the NULL character.
        """
        return self._driver_operation_io_resource_descriptor

    @property
    def simulate(self):
        """
        If True, the IVI specific driver simulates instrument driver I/O
        operations. If False, the IVI specific driver communicates directly with
        the instrument.

        If simulation is enabled, the specific driver functions do not perform
        instrument I/O. For output parameters that represent instrument data, the
        specific driver functions return simulated values.

        The default value is False. When the user opens an instrument session
        through an IVI class driver or uses a logical name to initialize an IVI
        specific driver, the user can override this value by specifying a value in
        the IVI configuration store. The Initialize function allows the user to
        override both the default value and the value that the user specifies in
        the IVI configuration store.
        """
        return self._driver_operation_simulate

    @simulate.setter
    def simulate(self, value):
        value = bool(value)
        if self._driver_operation_simulate and not value:
            raise SimulationStateException()
        self._driver_operation_simulate = value

    def clear_interchange_warnings(self):
        """
        This function clears the list of interchangeability warnings that the IVI
        specific driver maintains.

        When this function is called on an IVI class driver session, the function
        clears the list of interchangeability warnings that the class driver and
        the specific driver maintain.

        Refer to the Interchange Check attribute for more information on
        interchangeability checking.
        """
        self._driver_operation_interchange_warnings = list()

    def next_coercion_record(self):
        """
        If the Record Value Coercions attribute is set to True, the IVI specific
        driver keeps a list of all value coercions it makes on integer and
        floating point attributes. This function obtains the coercion information
        associated with the IVI session. It retrieves and clears the oldest
        instance in which the specific driver coerced a value the user specified
        to another value.

        The function returns an empty string in the CoercionRecord parameter if no
        coercion records remain for the session.

        The coercion record string shall contain the following information:

        * The name of the attribute that was coerced. This can be the generic name,
          the COM property name, or the C defined constant.
        * If the attribute applies to a repeated capability, the name of the
          virtual or physical repeated capability identifier.
        * The value that the user specified for the attribute.
        * The value to which the attribute was coerced.

        A recommended format for the coercion record string is as follows::

            " Attribute " + <attribute name> + [" on <repeated capability> " +
            <repeated capability identifier>] + " was coerced from " +
            <desiredVal> + " to " + <coercedVal>

        .

        And example coercion record string is as follows::

            Attribute TKTDS500_ATTR_VERTICAL_RANGE on channel ch1 was coerced from
            9.0 to 10.0.

        """
        if len(self._driver_operation_coercion_records) > 0:
            return self._driver_operation_coercion_records.pop()
        return ""

    def next_interchange_warning(self):
        """
        If the Interchange Check attribute is set to True, the IVI specific driver
        keeps a list of all interchangeability warnings that it encounters. This
        function returns the interchangeability warnings associated with the IVI
        session. It retrieves and clears the oldest interchangeability warning
        from the list. Interchangeability warnings indicate that using the
        application with a different instrument might cause different behavior.

        When this function is called on an IVI class driver session, it may return
        interchangeability warnings generated by the IVI class driver as well as
        interchangeability warnings generated by the IVI specific driver. The IVI
        class driver determines the relative order in which the IVI class driver
        warnings are returned in relation to the IVI specific driver warnings.

        The function returns an empty string in the InterchangeWarning parameter
        if no interchangeability warnings remain for the session.

        Refer to the Interchange Check attribute for more information on
        interchangeability checking.
        """
        if len(self._driver_operation_interchange_warnings) > 0:
            return self._driver_operation_interchange_warnings.pop()
        return ""

    @abc.abstractmethod
    def invalidate_all_attributes(self):
        """
        This function invalidates the cached values of all attributes for the
        session.
        """
        pass

    @abc.abstractmethod
    def reset_interchange_check(self):
        """
        This function resets the interchangeability checking algorithms of the IVI
        specific driver so that specific driver functions that execute prior to
        calling this function have no effect on whether future calls to the
        specific driver generate interchangeability warnings.
        
        When developing a complex test system that consists of multiple test
        modules, it is generally a good idea to design the test modules so that
        they can run in any order. To do so requires ensuring that each test
        module completely configures the state of each instrument it uses. If a
        particular test module does not completely configure the state of an
        instrument, the state of the instrument depends on the configuration from
        a previously executed test module. If the test modules execute in a
        different order, the behavior of the instrument and therefore the entire
        test module is likely to change. This change in behavior is generally
        instrument specific and represents an interchangeability problem.
        
        Users can use this function to test for such cases. By calling this
        function at the beginning of a test module, users can determine whether
        the test module has dependencies on the operation of previously executed
        test modules. Any interchangeability warnings that occur after the user
        calls this function indicate that the section of the test program that
        executes after this function and prior to the generation of the warning
        does not completely configure the instrument and that the user is likely
        to experience different behavior if the user changes the execution order
        of the test modules or if the user changes instruments.
        
        Note: This function does not clear interchangeability warnings from the
        list of interchangeability warnings. To guarantee that the Get Next
        Interchange Warning function returns interchangeability warnings that
        occur only after the program calls function, the user must clear the list
        of interchangeability warnings by calling the Clear Interchange Warnings
        function.
        
        Refer to the Interchange Check attribute for more information on
        interchangeability checking.
        """
        pass


class DriverIdentity(abc.ABC):
    "Inherent IVI methods for identification"

    def __init__(self, *args, **kwargs):
        super(DriverIdentity, self).__init__()

        self._identity_description = "Base IVI Driver"
        self._identity_identifier = ""
        self._identity_revision = ""
        self._identity_vendor = ""
        self._identity_instrument_manufacturer = "Cannot query from instrument"
        self._identity_instrument_model = "Cannot query from instrument"
        self._identity_instrument_firmware_revision = "Cannot query from instrument"
        self._identity_specification_major_version = 0
        self._identity_specification_minor_version = 0
        self._identity_supported_instrument_models = list()
        self._identity_group_capabilities = list()
        self.__dict__.setdefault('_identity_group_capabilities', list())

    def _add_group_capability(self, name):
        self.__dict__.setdefault('_identity_group_capabilities', list())
        self._identity_group_capabilities.insert(0, name)

    def description(self):
        """
        Returns a brief description of the IVI software component.

        The string that this attribute returns has no maximum size.
        """
        return self._identity_description

    def identifier(self):
        """
        Returns the case-sensitive unique identifier of the IVI software
        component. The string that this attribute returns contains a maximum of 32
        characters including the NULL character.
        """
        return self._identity_identifier

    def revision(self):
        """
        Returns version information about the IVI software component. Refer to
        Section 3.1.2.2, Additional Compliance Rules for Revision String
        Attributes, for additional rules regarding this attribute.

        The string that this attribute returns has no maximum size.
        """
        return self._identity_revision

    def vendor(self):
        """
        Returns the name of the vendor that supplies the IVI software component.

        The string that this attribute returns has no maximum size.
        """
        return self._identity_vendor

    def instrument_manufacturer(self):
        """
        Returns the name of the manufacturer of the instrument. The IVI specific
        driver returns the value it queries from the instrument as the value of
        this attribute or a string indicating that it cannot query the instrument
        identity.

        In some cases, it is not possible for the specific driver to query the
        manufacturer of the instrument. This can occur when the Simulate attribute
        is set to True or if the instrument is not capable of returning the
        manufacturer. For these cases, the specific driver returns defined strings
        for this attribute. If the Simulate attribute is set to True, the specific
        driver returns "Not available while simulating" as the value of this
        attribute. If the instrument is not capable of returning the manufacturer
        and the Simulate attribute is set to False, the specific driver returns
        "Cannot query from instrument" as the value of this attribute.

        The string that this attribute returns does not have a predefined maximum
        length.
        """
        return self._identity_instrument_manufacturer

    def instrument_model(self):
        """
        Returns the model number or name of the physical instrument. The IVI
        specific driver returns the value it queries from the instrument or a
        string indicating that it cannot query the instrument identity.

        In some cases, it is not possible for the specific driver to query the
        model of the instrument. This can occur when the Simulate attribute is
        set to True or if the instrument is not capable of returning the model.
        For these cases, the specific driver returns defined strings for this
        attribute. If the Simulate attribute is set to True, the specific driver
        returns "Not available while simulating" as the value of this attribute.
        If the instrument is not capable of returning the model and the Simulate
        attribute is set to False, the specific driver returns "Cannot query
        from instrument" as the value of this attribute.

        The string that this attribute returns does not have a predefined maximum
        length.
        """
        return self._identity_instrument_model

    def instrument_firmware_revision(self):
        """
        Returns an instrument specific string that contains the firmware
        revision information of the physical instrument. The IVI specific driver
        returns the value it queries from the instrument as the value of this
        attribute or a string indicating that it cannot query the instrument
        identity.

        In some cases, it is not possible for the specific driver to query the
        firmware revision of the instrument. This can occur when the Simulate
        attribute is set to True or if the instrument is not capable of returning
        the firmware revision. For these cases, the specific driver returns
        defined strings for this attribute. If the Simulate attribute is set to
        True, the specific driver returns "Not available while simulating" as the
        value of this attribute. If the instrument is not capable of returning the
        firmware version and the Simulate attribute is set to False, the specific
        driver returns "Cannot query from instrument" as the value of this
        attribute.

        The string that this attribute returns does not have a predefined maximum
        length.
        """
        return self._identity_instrument_firmware_revision

    def specification_major_version(self):
        """
        Returns the major version number of the class specification in accordance
        with which the IVI software component was developed. The value is a
        positive integer value.

        If the software component is not compliant with a class specification, the
        software component returns zero as the value of this attribute.
        """
        return self._identity_specification_major_version

    def specification_minor_version(self):
        """
        Returns the minor version number of the class specification in accordance
        with which the IVI software component was developed. The value is a
        positive integer value.

        If the software component is not compliant with a class specification, the
        software component returns zero as the value of this attribute.
        """
        return self._identity_specification_minor_version

    def group_capabilities(self):
        """
        Returns a list of names of class capability groups that the IVI specific
        driver implements. The items in the list are capability group names that
        the IVI class specifications define. The list is returned as a list of
        strings.

        If the IVI specific driver does not comply with an IVI class specification,
        the specific driver returns an array with zero elements.
        """
        return self._identity_group_capabilities

    @property
    def supported_instrument_models(self):
        """
        Returns a list of names of instrument models with which the IVI specific
        driver is compatible. The list is returned as a list of strings. For
        example, this attribute might return the strings "TKTDS3012", "TKTDS3014",
        and "TKTDS3016" .

        It is not necessary for the string to include the abbreviation for the
        manufacturer if it is the same for all models. In the example above, it is
        valid for the attribute to return the strings "TDS3012", "TDS3014", and
        "TDS3016".
        """
        return self._identity_supported_instrument_models


class DriverUtility(abc.ABC):
    "Inherent IVI utility methods"

    def __init__(self, *args, **kwargs):
        super(DriverUtility, self).__init__(*args, **kwargs)

    @abc.abstractmethod
    def disable(self):
        """
        The Disable operation places the instrument in a quiescent state as
        quickly as possible. In a quiescent state, an instrument has no or minimal
        effect on the external system to which it is connected. The Disable
        operation might be similar to the Reset operation in that it places the
        instrument in a known state. However, the Disable operation does not
        perform the other operations that the Reset operation performs such as
        configuring the instrument options on which the IVI specific driver
        depends. For some instruments, the disable function may do nothing.

        The IVI class specifications define the exact behavior of this function
        for each instrument class. Refer to the IVI class specifications for more
        information on the behavior of this function.
        """
        pass

    @abc.abstractmethod
    def error_query(self):
        """
        Queries the instrument and returns instrument specific error information.

        Generally, the user calls this function after another function in the IVI
        driver returns the Instrument Status error. The IVI specific driver
        returns the Instrument Status error when the instrument indicates that it
        encountered an error and its error queue is not empty. Error Query
        extracts an error out of the instrument's error queue.

        For instruments that have status registers but no error queue, the IVI
        specific driver emulates an error queue in software.

        The method returns a tuple containing the error code and error message.
        """
        error_code = 0
        error_message = "No error"
        return (error_code, error_message)

    @abc.abstractmethod
    def lock_object(self):
        """
        This function obtains a multithread lock for this instance of the driver.
        Before it does so, Lock Session waits until all other execution threads
        have released their locks or for the length of time specified by the
        maximum time parameter, whichever come first. The type of lock obtained
        depends upon the parameters passed to the specific driver constructor.

        The user can use Lock Session with IVI specific drivers to protect a
        section of code that requires exclusive access to the instrument. This
        occurs when the user takes multiple actions that affect the instrument
        and the user wants to ensure that other execution threads do not disturb
        the instrument state until all the actions execute. For example, if the
        user sets various instrument attributes and then triggers a measurement,
        the user must ensure no other execution thread modifies the attribute
        values until the user finishes taking the measurement.

        It is important to note that this lock is not related to I/O locks such as
        the VISA resource locking mechanism.

        The user can safely make nested calls to Lock Session within the same
        thread. To completely unlock the session, the user must balance each call
        to Lock Session with a call to Unlock Session. Calls to Lock Session must
        always obtain the same lock that is used internally by the IVI driver to
        guard individual method calls.
        """
        pass

    @abc.abstractmethod
    def reset(self):
        """
        This function performs the following actions:

        * Places the instrument in a known state. In an IEEE 488.2 instrument, the
          Reset function sends the command string ``*RST`` to the instrument.
        * Configures instrument options on which the IVI specific driver depends.
          A specific driver might enable or disable headers or enable binary mode
          for waveform transfers.

        The user can either call the Reset function separately or specify that it
        be called from the Initialize function. The Initialize function performs
        additional operations after performing the reset operation to place the
        instrument in a state more suitable for interchangeable programming. To
        reset the device and perform these additional operations, call the Reset
        With Defaults function instead of the Reset function.
        """
        pass

    @abc.abstractmethod
    def reset_with_defaults(self):
        """
        The Reset With Defaults function performs the same operations that the
        Reset function performs and then performs the following additional
        operations in the specified order:

        * Disables the class extension capability groups that the IVI specific
          driver implements.
        * If the class specification with which the IVI specific driver is
          compliant defines initial values for attributes, this function sets
          those attributes to the initial values that the class specification
          defines.
        * Configures the initial settings for the specific driver and instrument
          based on the information retrieved from the IVI configuration store when
          the instrument driver session was initialized.

        Notice that the Initialize function also performs these functions. To
        place the instrument and the IVI specific driver in the exact same state
        that they attain when the user calls the Initialize function, the user
        must first call the Close function and then the Initialize function.
        """
        self.reset()

    @abc.abstractmethod
    def self_test(self):
        """
        Causes the instrument to perform a self test. Self Test waits for the
        instrument to complete the test. It then queries the instrument for the
        results of the self test and returns the results to the user.

        If the instrument passes the self test, this function returns the tuple::

            (0, 'Self test passed')

        Otherwise, the function returns a tuple of the result code and message.
        """
        code = 0
        message = "Self test passed"
        return (code, message)

    @abc.abstractmethod
    def unlock_object(self):
        """
        This function releases a lock that the Lock Session function acquires.

        Refer to Lock Session for additional information on IVI session locks.
        """
        pass


class Driver(DriverOperation, DriverIdentity, DriverUtility):
    "Inherent IVI methods for all instruments"

    def __init__(self, resource=None, id_query=False, reset=False, *args, **kwargs):
        # process out args for initialize
        kw = {}
        for k in ('range_check', 'query_instr_status', 'cache', 'simulate', 'record_coercions',
                  'interchange_check', 'driver_setup', 'prefer_pyvisa'):
            if k in kwargs:
                kw[k] = kwargs.pop(k)

        self._interface = None
        self._initialized = False
        self.__dict__.setdefault('_instrument_id', '')
        self._cache_valid = dict()

        super(Driver, self).__init__(*args, **kwargs)

        # inherit prefer_pyvisa from global setting
        self._prefer_pyvisa = _prefer_pyvisa

        # call initialize if resource string or other args present
        self._initialized_from_constructor = False
        if resource is not None or len(kw) > 0:
            self._initialized_from_constructor = True
            self.initialize(resource, id_query, reset, **kw)

    def initialize(self, resource=None, id_query=False, reset=False, **keywargs):
        """
        The user must call the Initialize function prior to calling other IVI
        driver functions that access the instrument. The Initialize function is
        called automatically by the constructor if a resource string is passed as
        the first argument to the constructor.

        If simulation is disabled when the user calls the Initialize function, the
        function performs the following actions:

        * Opens and configures an I/O session to the instrument.
        * If the user passes True for the IdQuery parameter, the function queries
          the instrument for its ID and verifies that the IVI specific driver
          supports the particular instrument model. If the instrument cannot
          return its ID, the specific driver returns the ID Query Not Supported
          warning.
        * If the user passes True for the Reset parameter, the function places the
          instrument in a known state. In an IEEE 488.2 instrument, the function
          sends the command string "*RST" to the instrument. If the instrument
          cannot perform a reset, the IVI specific driver returns the Reset Not
          Supported warning.
        * Configures instrument options on which the IVI specific driver depends.
          For example, a specific driver might enable or disable headers or enable
          binary mode for waveform transfers.
        * Performs the following operations in the given order:
            1. Disables the class extension capability groups that the IVI
               specific driver does not implement.
            2. If the class specification with which the IVI specific driver is
               compliant defines initial values for attributes, this function sets
               the attributes to the values that the class specification defines.
            3. If the ResourceName parameter is a logical name, the IVI specific
               driver configures the initial settings for the specific driver and
               instrument based on the configuration of the logical name in the IVI
               configuration store.

        If simulation is enabled when the user calls the Initialize function, the
        function performs the following actions:

        * If the user passes True for the IdQuery parameter and the instrument
          cannot return its ID, the IVI specific driver returns the ID Query Not
          Supported warning.
        * If the user passes True for the Reset parameter and the instrument
          cannot perform a reset, the IVI specific driver returns the Reset Not
          Supported warning.
        * If the ResourceName parameter is a logical name, the IVI specific driver
          configures the initial settings for the specific driver based on the
          configuration of the logical name in the IVI configuration store.

        Some instrument driver operations require or take into account information
        from the IVI configuration store. Examples of such information are virtual
        repeated capability name mappings and the value of certain inherent
        attributes. An IVI driver shall retrieve all the information for a session
        from the IVI configuration store during the Initialization function. The
        IVI driver shall not read any information from the IVI configuration store
        for a session after the Initialization function completes. Refer to
        Section 3.2.3, Instantiating the Right Configuration Store From Software
        Modules, of IVI-3.5: Configuration Server Specification for details on how
        to correctly instantiate the configuration store.

        The ResourceName parameter must contain either a logical name that is
        defined in the IVI configuration store or an instrument specific string
        that identifies the I/O address of the instrument, such as a VISA resource
        descriptor string. Refer to IVI-3.5: Configuration Server Specification
        for restrictions on the format of IVI logical names. Refer to the
        VXIplug&play specifications for the grammar of VISA resource descriptor
        strings.

        Example resource strings::

            'TCPIP::10.0.0.1::INSTR'
            'TCPIP0::10.0.0.1::INSTR'
            'TCPIP::10.0.0.1::gpib,5::INSTR'
            'TCPIP0::10.0.0.1::gpib,5::INSTR'
            'TCPIP0::10.0.0.1::usb0::INSTR'
            'TCPIP0::10.0.0.1::usb0[1234::5678::MYSERIAL::0]::INSTR'
            'USB::1234::5678::INSTR'
            'USB::1234::5678::SERIAL::INSTR'
            'USB0::0x1234::0x5678::INSTR'
            'USB0::0x1234::0x5678::SERIAL::INSTR'
            'GPIB::10::INSTR'
            'GPIB0::10::INSTR'
            'ASRL1::INSTR'
            'ASRL::COM1,9600,8n1::INSTR'
            'ASRL::/dev/ttyUSB0,9600::INSTR'
            'ASRL::/dev/ttyUSB0,9600,8n1::INSTR'

        The user can use additional parameters to specify the initial values of
        certain IVI inherent attributes for the session. The following table lists
        the inherent attributes that the user can set through these named
        parameters. The user does not have to specify all or any of the
        attributes. If the user does not specify the initial value of an inherent
        attribute, the initial value of the attribute depends on the value of the
        ResourceName parameter:

        * If the ResourceName parameter contains an IVI logical name, the IVI
          specific driver configures the initial settings based on the
          configuration of the logical name in the IVI configuration store.
        * If the ResourceName parameter contains a resource descriptor string that
          identifies the I/O address of the instrument, the IVI specific driver
          sets inherent attributes to their default initial values. The following
          table shows the default initial value for each attribute.

        The following table lists the IVI inherent attributes that the user can
        set, their default initial values, and the name that represents each
        attribute. These options are passed to the initialize function or the
        constructor as key-value pairs.

        +-------------------------+----------------------+---------------------+
        | Attribute               | Default Inital Value | Options String Name |
        +=========================+======================+=====================+
        | Range Check             | True                 | range_check         |
        +-------------------------+----------------------+---------------------+
        | Query Instrument Status | False                | query_instr_status  |
        +-------------------------+----------------------+---------------------+
        | Cache                   | True                 | cache               |
        +-------------------------+----------------------+---------------------+
        | Simulate                | False                | simulate            |
        +-------------------------+----------------------+---------------------+
        | Record Value Coercions  | False                | record_coercions    |
        +-------------------------+----------------------+---------------------+
        | Interchange Check       | False                | interchange_check   |
        +-------------------------+----------------------+---------------------+
        | Driver Setup            | ''                   | driver_setup        |
        +-------------------------+----------------------+---------------------+
        | Prefer PyVISA           | False                | prefer_pyvisa       |
        +-------------------------+----------------------+---------------------+

        Each IVI specific driver defines it own meaning and valid values for the
        Driver Setup attribute. Many specific drivers ignore the value of the
        Driver Setup attribute. Other specific drivers use the Driver Setup string
        to configure instrument specific features at initialization. For example,
        if a specific driver supports a family of instrument models, the driver
        can use the Driver Setup attribute to allow the user to specify a
        particular instrument model to simulate.

        If the user attempts to initialize the instrument a second time without
        first calling the Close function, the Initialize function returns the
        Already Initialized error.
        """

        # decode options
        for op in keywargs:
            val = keywargs[op]
            if op == 'range_check':
                self._driver_operation_range_check = bool(val)
            elif op == 'query_instr_status':
                self._driver_operation_query_instrument_status = bool(val)
            elif op == 'cache':
                self._driver_operation_cache = bool(val)
            elif op == 'simulate':
                self._driver_operation_simulate = bool(val)
            elif op == 'record_coercions':
                self._driver_operation_record_coercions = bool(val)
            elif op == 'interchange_check':
                self._driver_operation_interchange_check = bool(val)
            elif op == 'driver_setup':
                self._driver_operation_driver_setup = val
            elif op == 'prefer_pyvisa':
                self._prefer_pyvisa = bool(val)
            else:
                raise UnknownOptionException('Invalid option')

        # process resource
        if self._driver_operation_simulate:
            print("Simulating; ignoring resource")
        elif resource is None:
            raise IOException('No resource specified!')
        elif type(resource) == str:
            # parse VISA resource string
            # valid resource strings:
            # TCPIP::10.0.0.1::INSTR
            # TCPIP0::10.0.0.1::INSTR
            # TCPIP::10.0.0.1::gpib,5::INSTR
            # TCPIP0::10.0.0.1::gpib,5::INSTR
            # TCPIP0::10.0.0.1::usb0::INSTR
            # TCPIP0::10.0.0.1::usb0[1234::5678::MYSERIAL::0]::INSTR
            # USB::1234::5678::INSTR
            # USB::1234::5678::SERIAL::INSTR
            # USB0::0x1234::0x5678::INSTR
            # USB0::0x1234::0x5678::SERIAL::INSTR
            # USB0::0x1234::0x5678::SERIAL::0::INSTR
            # GPIB::10::INSTR
            # GPIB0::10::INSTR
            # ASRL1::INSTR
            # ASRL::COM1,9600,8n1::INSTR
            # ASRL::/dev/ttyUSB0,9600::INSTR
            # ASRL::/dev/ttyUSB0,9600,8n1::INSTR
            m = re.match(
                '^(?P<prefix>(?P<type>TCPIP|USB|GPIB|ASRL)\d*)(::(?P<arg1>[^\s:]+))?(::(?P<arg2>[^\s:]+(\[.+\])?))?(::(?P<arg3>[^\s:]+))?(::(?P<arg4>[^\s:]+))?(::(?P<suffix>INSTR))$',
                resource, re.I)
            if m is None:
                if 'pyvisa' in globals():
                    # connect with PyVISA
                    self._interface = pyvisa.PyVisaInstrument(resource)
                else:
                    raise IOException('Invalid resource string')
            else:
                res_type = m.group('type').upper()
                res_prefix = m.group('prefix')
                res_arg1 = m.group('arg1')
                res_arg2 = m.group('arg2')
                res_arg3 = m.group('arg3')
                res_suffix = m.group('suffix')

                if res_type == 'TCPIP':
                    # TCP connection
                    if self._prefer_pyvisa and 'pyvisa' in globals():
                        # connect with PyVISA
                        self._interface = pyvisa.PyVisaInstrument(resource)
                    elif 'vxi11' in globals():
                        # connect with VXI-11
                        self._interface = vxi11.Instrument(resource)
                    elif 'pyvisa' in globals():
                        # connect with PyVISA
                        self._interface = pyvisa.PyVisaInstrument(resource)
                    else:
                        raise IOException('Cannot use resource type %s' % res_type)
                elif res_type == 'USB':
                    # USB connection
                    if self._prefer_pyvisa and 'pyvisa' in globals():
                        # connect with PyVISA
                        self._interface = pyvisa.PyVisaInstrument(resource)
                    elif 'usbtmc' in globals():
                        # connect with USBTMC
                        self._interface = usbtmc.Instrument(resource)
                    elif 'pyvisa' in globals():
                        # connect with PyVISA
                        self._interface = pyvisa.PyVisaInstrument(resource)
                    else:
                        raise IOException('Cannot use resource type %s' % res_type)
                elif res_type == 'GPIB':
                    # GPIB connection
                    if self._prefer_pyvisa and 'pyvisa' in globals():
                        # connect with PyVISA
                        self._interface = pyvisa.PyVisaInstrument(resource)
                    elif 'linuxgpib' in globals():
                        # connect with linux-gpib
                        self._interface = linuxgpib.LinuxGpibInstrument(resource)
                    elif 'pyvisa' in globals():
                        # connect with PyVISA
                        self._interface = pyvisa.PyVisaInstrument(resource)
                    else:
                        raise IOException('Cannot use resource type %s' % res_type)
                elif res_type == 'ASRL':
                    # Serial connection
                    if self._prefer_pyvisa and 'pyvisa' in globals():
                        # connect with PyVISA
                        self._interface = pyvisa.PyVisaInstrument(resource)
                    elif 'pyserial' in globals():
                        # connect with PySerial
                        self._interface = pyserial.SerialInstrument(resource)
                    elif 'pyvisa' in globals():
                        # connect with PyVISA
                        self._interface = pyvisa.PyVisaInstrument(resource)
                    else:
                        raise IOException('Cannot use resource type %s' % res_type)

                elif 'pyvisa' in globals():
                    # connect with PyVISA
                    self._interface = pyvisa.PyVisaInstrument(resource)
                else:
                    raise IOException('Unknown resource type %s' % res_type)

            self._driver_operation_io_resource_descriptor = resource

        elif 'vxi11' in globals() and resource.__class__ == vxi11.Instrument:
            # Got a vxi11 instrument, can use it as is
            self._interface = resource
        elif 'usbtmc' in globals() and resource.__class__ == usbtmc.Instrument:
            # Got a usbtmc instrument, can use it as is
            self._interface = resource
        elif {'read_raw', 'write_raw'}.issubset(set(resource.__class__.__dict__)):
            # has read_raw and write_raw, so should be a usable interface
            self._interface = resource
        else:
            # don't have a usable resource
            raise IOException('Invalid resource')

        self.invalidate_all_attributes()

        self._initialized = True

    def close(self):
        """
        When the user finishes using a Python IVI driver, the user should call
        either the Close method or __del__.  Note that __del__ will call close
        automatically.

        This function also does the following:

        * Prevents the user from calling other functions in the driver that
          access the instrument until the user calls the Initialize function
          again.
        * May deallocate internal resources used by the IVI session.
        """
        if self._interface:
            try:
                self._interface.close()
            except:
                pass

        self._interface = None
        self._initialized = False

    @property
    def initialized(self):
        """
        Returns a value that indicates whether the IVI specific driver is in the
        initialized state. After the specific driver is instantiated and before
        the Initialize function successfully executes, this attribute returns
        False. After the Initialize function successfully executes and prior to
        the execution of the Close function, this attribute returns True. After
        the Close function executes, this attribute returns False. 
        
        The Initialized attribute is one of the few IVI specific driver attributes
        that can be accessed while the specific driver is not in the initialized
        state. All the attributes of an IVI specific driver that can be accessed
        while the specific driver is not in the initialized state are listed below.
        
        * Component Class Spec Major Version
        * Component Class Spec Minor Version
        * Component Description
        * Component Prefix
        * Component Identifier
        * Component Revision
        * Component Vendor
        * Initialized
        * Supported Instrument Models
        """
        return self._initialized

    @staticmethod
    def _get_cache_tag(tag=None, skip=1):
        if tag is None:
            stack = inspect.stack()
            start = 0 + skip
            if len(stack) < start + 1:
                return ''
            tag = stack[start][3]

        if tag[0:4] == "_get": tag = tag[4:]
        if tag[0:4] == "_set": tag = tag[4:]
        if tag[0] == "_": tag = tag[1:]

        return tag

    def _get_cache_valid(self, tag=None, index=-1, skip_disable=False):
        if not skip_disable and not self._driver_operation_cache:
            return False
        tag = self._get_cache_tag(tag, 2)
        if index >= 0:
            tag = tag + '_%d' % index
        try:
            return self._cache_valid[tag]
        except KeyError:
            self._cache_valid[tag] = False
            return False

    def _set_cache_valid(self, valid=True, tag=None, index=-1):
        tag = self._get_cache_tag(tag, 2)
        if index >= 0:
            tag = tag + '_%d' % index
        self._cache_valid[tag] = valid

    def _driver_operation_invalidate_all_attributes(self):
        self._cache_valid = dict()

    def _write_raw(self, data):
        "Write binary data to instrument"
        if self._driver_operation_simulate:
            print("[simulating] Call to write_raw")
            return
        if not self._initialized or self._interface is None:
            raise NotInitializedException()
        self._interface.write_raw(data)

    def _read_raw(self, num=-1):
        "Read binary data from instrument"
        if self._driver_operation_simulate:
            print("[simulating] Call to read_raw")
            return b''
        if not self._initialized or self._interface is None:
            raise NotInitializedException()
        return self._interface.read_raw(num)

    def _ask_raw(self, data, num=-1):
        "Write then read binary data"
        if self._driver_operation_simulate:
            print("[simulating] Call to ask_raw")
            return b''
        if not self._initialized or self._interface is None:
            raise NotInitializedException()
        try:
            return self._interface.ask_raw(data, num)
        except AttributeError:
            # if interface does not implement ask_raw, emulate it
            self._write_raw(data)
            return self._read_raw(num)

    def _write(self, data, encoding='utf-8'):
        "Write string to instrument"
        if self._driver_operation_simulate:
            print("[simulating] Write (%s) '%s'" % (encoding, data))
            return
        if not self._initialized or self._interface is None:
            raise NotInitializedException()
        try:
            self._interface.write(data, encoding)
        except AttributeError:
            if type(data) is tuple or type(data) is list:
                # recursive call for a list of commands
                for data_i in data:
                    self._write(data_i, encoding)
                return

            self._write_raw(str(data).encode(encoding))

    def _read(self, num=-1, encoding='utf-8'):
        "Read string from instrument"
        if self._driver_operation_simulate:
            print("[simulating] Read (%s)" % encoding)
            return ''
        if not self._initialized or self._interface is None:
            raise NotInitializedException()
        try:
            return self._interface.read(num, encoding)
        except AttributeError:
            return self._read_raw(num).decode(encoding).rstrip('\r\n')

    def _ask(self, data, num=-1, encoding='utf-8'):
        "Write then read string"
        if self._driver_operation_simulate:
            print("[simulating] Ask (%s) '%s'" % (encoding, data))
            return ''
        if not self._initialized or self._interface is None:
            raise NotInitializedException()
        try:
            return self._interface.ask(data, num, encoding)
        except AttributeError:
            # if interface does not implement ask, emulate it
            if type(data) is tuple or type(data) is list:
                #    # recursive call for a list of commands
                val = list()
                for data_i in data:
                    val.append(self._ask(data_i, num, encoding))
                return val

            self._write(data, encoding)
            return self._read(num, encoding)

    def _ask_for_values(self, msg, delim=',', converter=float, array=True):
        '''
        write then read a list or array of data
        
        Parameters
        --------------
        msg : str
            message to write to instrument
        delim : str
            delimeter
        converter : type
            a datatype used to typecase the elements in the returned list
        array: bool
            convert the output to a numpy array 
        
        '''
        s = self._ask(msg)
        s_split = s.split(delim)
        out = map(converter, s_split)
        if array:
            out = np.array(out)
        return out

    def _read_stb(self):
        "Read status byte"
        if self._driver_operation_simulate:
            print("[simulating] Read status")
            return 0
        if not self._initialized or self._interface is None:
            raise NotInitializedException()
        try:
            return self._interface.read_stb()
        except (AttributeError, NotImplementedError):
            return int(self._ask("*STB?"))

    def _trigger(self):
        "Device trigger"
        if self._driver_operation_simulate:
            print("[simulating] Trigger")
        if not self._initialized or self._interface is None:
            raise NotInitializedException()
        try:
            self._interface.trigger()
        except (AttributeError, NotImplementedError):
            self._write("*TRG")

    def _clear(self):
        "Device clear"
        if self._driver_operation_simulate:
            print("[simulating] Clear")
        if not self._initialized or self._interface is None:
            raise NotInitializedException()
        try:
            return self._interface.clear()
        except (AttributeError, NotImplementedError):
            self._write("*CLS")

    def _remote(self):
        "Device set remote"
        if self._driver_operation_simulate:
            print("[simulating] Remote")
        if not self._initialized or self._interface is None:
            raise NotInitializedException()
        return self._interface.remote()

    def _local(self):
        "Device set local"
        if self._driver_operation_simulate:
            print("[simulating] Local")
        if not self._initialized or self._interface is None:
            raise NotInitializedException()
        return self._interface.local()

    def _read_ieee_block(self):
        "Read IEEE block"
        # IEEE block binary data is prefixed with #lnnnnnnnn
        # where l is length of n and n is the
        # length of the data
        # ex: #800002000 prefixes 2000 data bytes

        ch = self._read_raw(1)

        if len(ch) == 0:
            return b''

        while ch != b'#':
            ch = self._read_raw(1)

        l = int(self._read_raw(1))
        if l > 0:
            num = int(self._read_raw(l))
            raw_data = self._read_raw(num)
        else:
            raw_data = self._read_raw()

        return raw_data

    def _ask_for_ieee_block(self, data, encoding='utf-8'):
        "Write string then read IEEE block"
        self._write(data, encoding)
        return self._read_ieee_block()

    def _write_ieee_block(self, data, prefix=None, encoding='utf-8'):
        "Write IEEE block"
        # IEEE block binary data is prefixed with #lnnnnnnnn
        # where l is length of n and n is the
        # length of the data
        # ex: #800002000 prefixes 2000 data bytes

        block = b''

        if type(prefix) == str:
            block = prefix.encode(encoding)
        elif type(prefix) == bytes:
            block = prefix

        block = block + build_ieee_block(data)

        self._write_raw(block)
