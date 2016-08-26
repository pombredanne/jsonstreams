# encoding=utf-8
# Copyright © 2016 Dylan Baker

# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:

# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.

# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.

"""A pure python implementaiotn of jsonstreams.

This is a pure python fallback for those that don't have cython or don't want
cython.
"""

import copy
import functools
try:
    import simplejson as json  # type: ignore
except ImportError:
    import json  # type: ignore

import six

__all__ = (
    'InvalidTypeError',
    'ModifyWrongStreamError',
    'StreamClosedError',
    'Stream',
)


class JSONStreamsError(Exception):
    """Base exception for jsonstreams."""


class StreamClosedError(JSONStreamsError):
    """Error raised when writing into a closed Element."""


class ModifyWrongStreamError(JSONStreamsError):
    """This exception is raised when writing to a parent when a child is opened.

    Because of the streaming nature of this module, one cannot write into a
    parent without first closing the child, since there is no way to put the
    data in the parent while the child is opened.

    This Exception should not be caught, it is a fatal exception.
    """


class InvalidTypeError(JSONStreamsError):
    """An exception raised when an invalid type is passed.

    Sometimes a type is invalid for certain purposes. For example, a numeric
    type or null cannot be used as a key in a JSON object.
    """


class BaseWriter(object):
    """Private class for writing things."""

    __slots__ = ('fd', 'indent', 'baseindent', 'encoder', 'pretty', 'comma',
                 'write', 'write_comma_literal')

    def __init__(self, fd, indent, baseindent, encoder, pretty):
        self.fd = fd  # pylint: disable=invalid-name
        self.indent = indent
        self.baseindent = baseindent
        self.encoder = encoder
        self.pretty = pretty
        self.comma = False

        if not pretty:
            self.write = self._write_no_comma
        else:
            self.write = self._pretty_write_no_comma

        if indent:
            self.write_comma_literal = functools.partial(
                self.raw_write, ',', newline=True)
        else:
            self.write_comma_literal = functools.partial(self.raw_write, ', ')

    def _indent(self):
        return ' ' * self.baseindent * self.indent

    def raw_write(self, value, indent=False, newline=False):
        if indent:
            self.fd.write(self._indent())
        self.fd.write(value)
        if newline:
            self.fd.write('\n')

    def _write_no_comma(self):
        """Baseish class."""

    def _write_comma(self):
        """Baseish class."""

    def _pretty_write_no_comma(self):
        """Baseish class."""

    def _pretty_write_comma(self):
        """Baseish class."""

    def set_comma(self):
        # replace with the comma version, removeing the need for extra if
        # statements.
        self.comma = True
        if not self.pretty:
            self.write = self._write_comma
        else:
            self.write = self._pretty_write_comma


class ObjectWriter(BaseWriter):
    """A Writer class specifically for Objects.

    Supports writing keys and values.
    """

    def write_key(self, key):
        """Write a key for an object.

        This will enforce that a key must be a string type, since that's a
        requirement of JSON.
        """
        if not isinstance(key, (six.text_type, six.binary_type)):
            raise InvalidTypeError('Only string or bytes types can be used as '
                                   'keys in JSON objects')
        self.raw_write(self.encoder.encode(key), indent=self.indent)
        self.raw_write(': ')

    def _write_no_comma(self, key, value):  # pylint: disable=arguments-differ
        """Write without a comma."""
        self.write_key(key)
        self.raw_write(self.encoder.encode(value))
        self.set_comma()

    def _write_comma(self, key, value):  # pylint: disable=arguments-differ
        """Write with a comma."""
        self.write_comma_literal()
        self.write_key(key)
        self.raw_write(self.encoder.encode(value))

    def _pretty_write_no_comma(self, key, value):
        """Write without a comma."""
        # pylint: disable=arguments-differ
        self.__pretty_write(key, value)
        self.set_comma()

    def _pretty_write_comma(self, key, value):
        """Write with a comma."""
        # pylint: disable=arguments-differ
        self.write_comma_literal()
        self.__pretty_write(key, value)

    def __pretty_write(self, key, value):
        """Write items into object with newlines and proper indenting.

        This shared private method shares code between the comman and no comma
        versions of pretty_write.
        """
        self.write_key(key)
        items = self.encoder.encode(value).rstrip().split('\n')
        # If the length of items is 1, then the for loop is dead code, and
        # the final write is incorrect.
        if len(items) > 1:
            self.raw_write(items[0], newline=True)
            for each in items[1:-1]:
                self.raw_write(each, indent=True, newline=True)
            self.raw_write(items[-1], indent=True)
        else:
            self.raw_write(items[0])


class ArrayWriter(BaseWriter):
    """Writer for Arrays.

    Supports writing only values.
    """

    def _write_no_comma(self, value):  # pylint: disable=arguments-differ
        """Write without a comma."""
        self.raw_write(self.encoder.encode(value), indent=self.indent)
        self.set_comma()

    def _write_comma(self, value):  # pylint: disable=arguments-differ
        """Write with a comma."""
        self.write_comma_literal()
        self.raw_write(self.encoder.encode(value), indent=self.indent)

    def _pretty_write_no_comma(self, value):
        """Write without a comma."""
        # pylint: disable=arguments-differ
        self.__pretty_write(value)
        self.set_comma()

    def _pretty_write_comma(self, value):  # pylint: disable=arguments-differ
        """Write with a comma."""
        self.write_comma_literal()
        self.__pretty_write(value)

    def __pretty_write(self, value):
        """Write elements into a list, but with proper newlines and indent."""
        items = self.encoder.encode(value).rstrip().split('\n')
        for each in items[:-1]:
            self.raw_write(each, indent=True, newline=True)
        self.raw_write(items[-1], indent=True)


def _raise(exc, *args, **kwargs):  # pylint: disable=unused-argument
    """Helper to raise an exception."""
    raise exc


class Open(object):
    """A helper to allow subelements to be used as context managers."""

    __slots__ = ('__inst', '__callback', 'subarray', 'subobject')

    def __init__(self, initializer, callback=None):
        self.__inst = initializer()
        self.__callback = callback
        self.subarray = self.__inst.subarray
        self.subobject = self.__inst.subobject

    def write(self, *args, **kwargs):
        self.__inst.write(*args, **kwargs)

    def __enter__(self):
        return self.__inst

    def close(self):
        self.__inst.close()
        if self.__callback is not None:
            self.__callback()

    def __exit__(self, etype, evalue, traceback):
        self.close()


class _CacheChild(object):
    """Object that hides public methods while a child is opened.

    It does this by shadowing them with a function that raises an exception
    when called, during initialization, and when it's restore() method is
    called it puts them back.
    """

    __slots__ = ('cached', 'inst')

    def __init__(self, inst, **kwargs):
        self.cached = kwargs
        self.inst = inst

        func = functools.partial(_raise, ModifyWrongStreamError(
            'Cannot modify a stream while a child stream is opened'))
        for k in six.iterkeys(kwargs):
            setattr(inst, k, func)

    def restore(self):
        for k, v in six.iteritems(self.cached):
            setattr(self.inst, k, v)


class Object(object):
    """A streaming array representation."""

    def __init__(self, fd, indent, baseindent, encoder, _indent=False,
                 pretty=False):
        self._writer = ObjectWriter(fd, indent, baseindent, encoder, pretty)
        self._writer.raw_write('{', indent=_indent, newline=indent)
        self._writer.baseindent += 1

    def _sub(self, jtype, key):
        """A shared method for subarray and subobject."""
        # Write in the comma if it's needed, then write in the key
        if self._writer.comma:
            self._writer.write_comma_literal()
        self._writer.set_comma()
        self._writer.write_key(key)

        # Create an object that caches the public methods of the class and
        # replaces them with a function that raises an exception. It's restore
        # method is passed as a callback to Open which is called when
        # Open.close() is called.
        cached = _CacheChild(
            self, write=self.write, subobject=self.subobject,
            subarray=self.subarray, close=self.close)

        return Open(
            functools.partial(
                jtype, self._writer.fd, self._writer.indent,
                self._writer.baseindent, self._writer.encoder,
                pretty=self._writer.pretty, _indent=False),
            callback=cached.restore)

    def subobject(self, key):  # pylint: disable=method-hidden
        return self._sub(Object, key)

    def subarray(self, key):  # pylint: disable=method-hidden
        return self._sub(Array, key)

    def write(self, key, value):  # pylint: disable=method-hidden
        return self._writer.write(key, value)

    def close(self):  # pylint: disable=method-hidden
        """Close the Object.

        Once this method is closed calling any of the public methods will
        result in an StreamClosedError being raised.
        """
        if self._writer.indent:
            self._writer.raw_write('\n')
        self._writer.baseindent -= 1
        self._writer.raw_write('}', indent=True)

        self.write = functools.partial(
            _raise, StreamClosedError('Cannot write into a closed object!'))
        self.close = functools.partial(
            _raise,
            StreamClosedError('Cannot close an already closed object!'))
        self.subarray = functools.partial(
            _raise,
            StreamClosedError('Cannot open a subarray of a closed object!'))
        self.subobject = functools.partial(
            _raise,
            StreamClosedError('Cannot open a subobject of a closed object!'))

    def iterwrite(self, args):
        """Write multiple keys and values into the object.

        This method takes tuples of (key, value) and writes them into the dict.

        It is a misuse of this api to write a dictionary using the items method
        (or iteritems, or viewitems) unless using them with filtering, it is
        meant for use with generators or the like.

        >>> gen = ((str(s), str(k)) for s in range(5) for k in range(5))
        >>> with Stream('object', filename='foo') as s:
        ...     s.iterwrite(gen)
        """
        for key, value in args:
            self._writer.write(key, value)

    def __enter__(self):
        return self

    def __exit__(self, etype, evalue, traceback):
        self.close()


class Array(object):
    """A streaming array representation."""

    def __init__(self, fd, indent, baseindent, encoder, _indent=False,
                 pretty=False):
        self._writer = ArrayWriter(fd, indent, baseindent, encoder, pretty)
        self._writer.raw_write('[', indent=_indent, newline=indent)
        self._writer.baseindent += 1

    def _sub(self, jtype):
        """A shared method for subarray and subobject."""
        # Write in the comma if it's needed, then write in the key
        if self._writer.comma:
            self._writer.write_comma_literal()
        self._writer.set_comma()

        # Create an object that caches the public methods of the class and
        # replaces them with a function that raises an exception. It's restore
        # method is passed as a callback to Open which is called when
        # Open.close() is called.
        cached = _CacheChild(
            self, write=self.write, subobject=self.subobject,
            subarray=self.subarray, close=self.close)

        return Open(
            functools.partial(
                jtype, self._writer.fd, self._writer.indent,
                self._writer.baseindent, self._writer.encoder,
                pretty=self._writer.pretty, _indent=True),
            callback=cached.restore)

    def subobject(self):  # pylint: disable=method-hidden
        return self._sub(Object)

    def subarray(self):  # pylint: disable=method-hidden
        return self._sub(Array)

    def write(self, value):  # pylint: disable=method-hidden
        return self._writer.write(value)

    def iterwrite(self, args):
        """Write multiple values into the array.

        This method takes an iterator of arguments

        It is a misuse of this api to write a dictionary using the items method
        (or iteritems, or viewitems) unless using them with filtering, it is
        meant for use with generators or the like.

        >>> gen = (str(s) for s in range(5))
        >>> with Stream('array', filename='foo') as s:
        ...     s.iterwrite(gen)
        """
        for value in args:
            self._writer.write(value)

    def close(self):  # pylint: disable=method-hidden
        """Close the Object.

        Once this method is closed calling any of the public methods will
        result in an StreamClosedError being raised.
        """
        if self._writer.indent:
            self._writer.raw_write('\n')
        self._writer.baseindent -= 1
        self._writer.raw_write(']', indent=True)

        self.write = functools.partial(
            _raise, StreamClosedError('Cannot write into a closed array!'))
        self.close = functools.partial(
            _raise,
            StreamClosedError('Cannot close an already closed array!'))
        self.subarray = functools.partial(
            _raise,
            StreamClosedError('Cannot open a subarray of a closed array!'))
        self.subobject = functools.partial(
            _raise,
            StreamClosedError('Cannot open a subobject of a closed array!'))

    def __enter__(self):
        return self

    def __exit__(self, etype, evalue, traceback):
        self.close()


class Stream(object):
    """A JSON stream object.

    This object is the "root" object for the stream. It handles opening and
    closing the file, and provides the ability to write into the stream, and to
    open sub elements.

    This element can be used as a context manager, which is the recommended way
    to use it.

    Arguments:
    filename -- the name of the file to open
    jtype    -- either 'object' or 'array', this will set the type of the
                stream's root.

    Keyword Arguments:
    indent   -- How much to indent each level, if set to 0 no indent will be
                used and the stream will be written in a single line.
                Default: 0
    encoder  -- A json.JSONEncoder instance. This will be used to encode
                objects passed to the write method of the Stream and all
                instances returned by the subarray and subobject methods of
                this instance and it's children.
                Default: json.JSONEncoder
    """

    _types = {
        'object': Object,
        'array': Array,
    }

    def __init__(self, jtype, filename=None, fd=None, indent=0, pretty=False,
                 encoder=json.JSONEncoder):
        """Constructor."""
        assert jtype in ['object', 'array']
        assert filename or fd

        self.__fd = fd or open(filename, 'w')
        self.__inst = self._types[jtype](
            self.__fd, indent, 0, encoder(indent=indent), pretty=pretty)

        self.subobject = self.__inst.subobject
        self.subarray = self.__inst.subarray

    def write(self, *args, **kwargs):
        """Write values into the stream.

        This method wraps either Object.write or Array.write, depending on
        whether it was initialzed with the 'object' argument or the 'array'
        argument.
        """
        self.__inst.write(*args, **kwargs)

    def iterwrite(self, *args, **kwargs):
        """Write values into the streams from an iterator."""
        self.__inst.iterwrite(*args, **kwargs)

    def close(self):
        """Close the root element and the file."""
        self.__inst.close()
        self.__fd.close()

    def __enter__(self):
        """Start context manager."""
        return self

    def __exit__(self, etype, evalue, traceback):
        """Exit context manager."""
        self.close()