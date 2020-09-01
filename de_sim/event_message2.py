""" Base class for event messages

:Author: Arthur Goldberg <Arthur.Goldberg@mssm.edu>
:Date: 2017-03-26
:Copyright: 2016-2020, Karr Lab
:License: MIT
"""

from abc import ABCMeta
import warnings

from de_sim.errors import SimulatorError
from de_sim.utilities import ConcreteABCMeta


class EventMessageNormalTop2(object):
    """ A 'normal' event message base class

    """
    def __init__(self):
        pass


class EventMessageInterface(object, metaclass=ABCMeta):
    """ An abstract base class for event messages

    The comparison operations (`__gt__`, `__lt__`, etc.) order event message instances by the
    tuple (class name, instance attribute values). When a simulation object executes multiple
    events simultaneously, this ensures that a list containing these messages can be sorted in
    a deterministic order, because the events' messages will have a unique sort order.

    Attributes:
        __slots__ (:obj:`list`): use `__slots__` to save memory because a simulation may contain many event messages
    """
    __slots__ = []

    def __init__(self, *args):
        """ Initialize an :obj:`EventMessage`

        Args:
            args (:obj:`tuple`): argument list for initializing a subclass instance

        Raises:
            :obj:`SimulatorError`: if `args` does not contain an argument for each entry in `__slots__`
        """
        if len(args) != len(self.__slots__):
            raise SimulatorError("Constructor for EventMessage '{}' expects {} argument(s), but "
                                 "{} provided".format(
                                     self.__class__.__name__, len(self.__slots__), len(args)))
        for slot, arg in zip(self.__slots__, args):
            setattr(self, slot, arg)

    def _values(self, to_str=False):
        """ Provide the values in an :obj:`EventMessage`

        Uninitialized attribute values are returned as `None`, or `str(None)` if `to_str` is set.

        Args:
            to_str (:obj:`bool`): if set, return `str()` of attribute values

        Returns:
            :obj:`list`: list of attribute values
        """
        vals = []
        for attr in self.__slots__:
            if hasattr(self, attr):
                if to_str:
                    vals.append(str(getattr(self, attr)))
                else:
                    vals.append(getattr(self, attr))
            else:
                if to_str:
                    vals.append(str(None))
                else:
                    vals.append(None)
        return vals

    def value_map(self):
        """ Provide a map from each attribute to its value, as a :obj:`str`, for this :obj:`EventMessage`

        Uninitialized values are returned as `str(None)`.

        Returns:
            :obj:`dict`: map attribute -> str(attribute value)
        """
        return {attr: val for attr, val in zip(self.__slots__, self._values(to_str=True))}

    def values(self, annotated=False, as_list=False, separator='\t'):
        """ Provide the values in this :obj:`EventMessage`

        Uninitialized values are returned as `str(None)`.

        Args:
            annotated (:obj:`bool`, optional): if set, prefix each value with its attribute name
            as_list (:obj:`bool`, optional): if set, return the attribute names in a :obj:`list`
            separator (:obj:`str`, optional): the field separator used if the attribute names
                are returned as a :obj:`str`

        Returns:
            :obj:`obj`: `None` if this message has no `msg_field_names`, or a :obj:`str` representation of
            the attribute names for this :obj:`EventMessage`, or a :obj:`list`
            representation if `as_list` is set
        """
        if not self.attrs():
            return None
        if annotated:
            list_repr = ["{}:{}".format(attr, val) for attr, val in
                         zip(self.__slots__, self._values(to_str=True))]
        else:
            list_repr = self._values(to_str=True)
        if as_list:
            return list_repr
        else:
            return separator.join(list_repr)

    def __str__(self):
        """ Provide a string representation of an :obj:`EventMessage`
        """
        return "EventMessage: {}({})".format(self.__class__.__name__, self.value_map())

    def attrs(self):
        """ Provide a list of the field names for this :obj:`EventMessage`

        Returns:
            :obj:`list` of :obj:`str`: the `msg_field_names` in this :obj:`EventMessage`
        """
        return self.__slots__

    def header(self, as_list=False, separator='\t'):
        """ Provide the attribute names for this :obj:`EventMessage`

        Args:
            as_list (:obj:`bool`, optional): if set, return the attribute names in a :obj:`list`
            separator (:obj:`str`, optional): the field separator used if the attribute names are returned
                as a string

        Returns:
            :obj:`obj`: `None` if this message has no `msg_field_names`, or a string representation of
            the attribute names for this :obj:`EventMessage`, or a :obj:`list`
            representation if `as_list` is set
        """
        if not self.attrs():
            return None
        if as_list:
            return self.attrs()
        else:
            return separator.join(self.attrs())

    def __lt__(self, other):
        """ Does this :obj:`EventMessage` sort before `other`?

        Args:
            other (:obj:`EventMessage`): another :obj:`EventMessage`

        Returns:
            :obj:`bool`: :obj:`True` if this :obj:`EventMessage` sorts before `other`
        """
        return (self.__class__.__name__, self._values()) < (other.__class__.__name__, other._values())

    def __le__(self, other):
        """ Does this :obj:`EventMessage` sort before or equal `other`?

        Args:
            other (:obj:`EventMessage`): another :obj:`EventMessage`

        Returns:
            :obj:`bool`: :obj:`True` if this :obj:`EventMessage` sorts before or equals `other`
        """
        return not (other < self)

    def __gt__(self, other):
        """ Does this :obj:`EventMessage` sort after `other`?

        Args:
            other (:obj:`EventMessage`): another :obj:`EventMessage`

        Returns:
            :obj:`bool`: :obj:`True` if this :obj:`EventMessage` sorts after `other`
        """
        return (self.__class__.__name__, self._values()) > (other.__class__.__name__, other._values())

    def __ge__(self, other):
        """ Does this :obj:`EventMessage` sort after or equal `other`?

        Args:
            other (:obj:`EventMessage`): another :obj:`EventMessage`

        Returns:
            :obj:`bool`: :obj:`True` if this :obj:`EventMessage` sorts after or equals `other`
        """
        return not (self < other)



class EventMessage2(EventMessageInterface, metaclass=CombinedEventMessageMeta):
    """ The event message base class

    Each simulation event contains an event message object. This
    module supports compact declaration of :obj:`EventMessage` subclasses. For example::

        class ExampleEventMessage1(EventMessage):
            " Docstring for ExampleEventMessage1 "
            msg_field_names = ['attr1', 'attr2']

    defines the `ExampleEventMessage1` class with a short docstring and message fields named
    `attr1` and `attr2`.

    :obj:`EventMessage` subclasses must support the comparison operations `<`, `<=`, etc. This is
    provided automatically for message fields that support comparison. :obj:`EventMessage` subclasses with
    message fields that do not support comparison must override `__lt__`, `__le__`, etc.
    """
    pass


class EventMessageNormalBottom2(object):
    """ A 'normal' event message base class

    """
    def __init__(self):
        pass

