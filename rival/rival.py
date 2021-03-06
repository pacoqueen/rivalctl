#!/usr/bin/env python
# -*- coding: utf-8 -*-

from __future__ import print_function
import os
import sys
import yaml
import pyudev
import hidrawpure as hidraw
import webcolors

DEBUG = True

RIVAL_HID_ID = '0003:00001038:00001384'     # SteelSeries Rival ¿300? ¿6500?
RIVAL100_HID_ID = '0003:00001038:00001702'     # SteelSeries Rival 100

LED_LOGO = 1
LED_WHEEL = 2

LED_STYLE_STEADY = 1
LED_STYLE_BREATHE_SLOW = 2
LED_STYLE_BREATHE_MEDIUM = 3
LED_STYLE_BREATHE_FAST = 4


###############################################################################
# Auxiliary functions
#

def find_device_path(hid_id):
    """Find the appropriate /dev/hidrawX device to control the mouse."""
    ctx = pyudev.Context()
    for dev in ctx.list_devices(HID_ID=hid_id):
        if dev.sequence_number == 0:
            children = list(dev.children)
            if children:
                child = children[0]
                if child.subsystem == 'hidraw':
                    return child['DEVNAME']


def open_hiddevice(hid_id, dev_path=None):
    """
    Open the device representing the mouse. If dev_path is None, it tries to
    find it.
    """
    if dev_path is None:
        dev_path = find_device_path(hid_id)
    try:
        device = hidraw.HIDRaw(open(dev_path, 'w+'))
    except PermissionError:
        print("You don't have write access to %s." % (dev_path))
        print("""
        Run this script with sudo or ensure that your user belongs to the
        same group as the device and you have write access. For instance:
          sudo groupadd rival
          sudo chown $(ls -l %s | cut -d ' ' -f 4):rival %s
          sudo adduser $(whoami) rival
          sudo chmod g+w %s
        And maybe create an udev rule like (as root):
          echo 'KERNEL=="hidraw*", GROUP="rival"' > /etc/10-local-rival.rules
          udevadm trigger
        """ % (dev_path, dev_path, dev_path))
        sys.exit(1)
    return device


def open_device(dev_path=None):
    """
    Open the HID device corresponding to the mouse. Returns a Rival object.
    """
    try:
        device = Rival100(dev_path=dev_path)
    except TypeError:   # Not a Rival 100. Default to generic ¿300?
        if DEBUG:
            print("Testing for generic SteelSeries Rival...")
        device = Rival(dev_path=dev_path)
    return device


def is_strtype(obj):
    """
    Return True if the object received is a string.
    """
    # FIXME: It is really necessary?
    try:
        return isinstance(obj, basestring)
    except NameError:
        return isinstance(obj, str)


###############################################################################
# Profiles for fast-switching configurations.
#

class Profile(object):

    def __init__(self):
        self._logo_color = (0, 0, 0)
        self._wheel_color = (0, 0, 0)
        self.logo_style = LED_STYLE_STEADY
        self.wheel_style = LED_STYLE_STEADY
        self.cpi1 = 800
        self.cpi2 = 1600
        self.polling_rate = 1000

    def _normalize_color(self, value):
        rgb = None
        try:
            if is_strtype(value):
                if value.startswith("#"):
                    rgb = webcolors.hex_to_rgb(value)
                else:
                    rgb = webcolors.name_to_rgb(value)
            elif hasattr(value, '__iter__'):
                rgb = tuple(value)
        except ValueError as e:
            print(e, file=sys.stderr)
        return rgb

    @property
    def logo_color(self):
        return self._logo_color

    @logo_color.setter
    def logo_color(self, value):
        rgb = self._normalize_color(value)
        if not rgb:
            raise ValueError("Invalid Color: %s" % (value,))
        self._logo_color = rgb

    @property
    def wheel_color(self):
        return self._wheel_color

    @wheel_color.setter
    def wheel_color(self, value):
        rgb = self._normalize_color(value)
        if not rgb:
            raise ValueError("Invalid Color: %s" % (value,))
        self._wheel_color = rgb

    @classmethod
    def copy_profile(cls, profile):
        newprofile = Profile()
        newprofile.logo_color = tuple(profile.logo_color)
        newprofile.wheel_color = tuple(profile.wheel_color)
        newprofile.logo_style = profile.logo_style
        newprofile.wheel_style = profile.wheel_style
        newprofile.cpi1 = profile.cpi1
        newprofile.cpi2 = profile.cpi2
        newprofile.polling_rate = profile.polling_rate
        return newprofile

    @classmethod
    def find_profile(cls, name):
        def find_profile_file(_dir):
            for f in os.listdir(_dir):
                n, x = os.path.splitext(f)
                if x.lower() in ('.yml', '.yaml', ''):
                    if n.lower() == name:
                        return os.path.join(_dir, f)
        if os.path.exists(name):
            return name
        f = find_profile_file(".")
        if f:
            return f
        rival_dir = os.path.join(os.path.expanduser("~"), ".rival")
        if os.path.exists(rival_dir):
            f = find_profile_file(rival_dir)
        if f:
            return f

    @classmethod
    def from_yaml(cls, stream):
        cfg = yaml.load(stream)
        profile = cls.copy_profile(cls.FACTORY_PROFILE)
        for k, v in cfg.items():
            if hasattr(profile, k):
                setattr(profile, k, v)
        return profile

    def to_report_list(self, current_state=None):
        items = [
            self.set_wheel_color(self.wheel_color),
            self.set_wheel_style(self.wheel_style),
            self.set_logo_color(self.logo_color),
            self.set_logo_style(self.logo_style),
            self.set_cpi_1(self.cpi1),
            self.set_cpi_2(self.cpi2),
            self.set_polling_rate(self.polling_rate)
        ]
        if current_state:
            return [i for i in items if i not in current_state]
        return items


###############################################################################
# Main classes for encapsulate mouse features.
#

class Rival(object):
    """
    Base class for generic a Rival mouse.
    """
    FACTORY_PROFILE = Profile()
    FACTORY_PROFILE.logo_color = (255, 24, 0)
    FACTORY_PROFILE.wheel_color = (255, 24, 0)
    FACTORY_PROFILE.logo_style = 2
    FACTORY_PROFILE.wheel_style = 2
    FACTORY_PROFILE.cpi1 = 800
    FACTORY_PROFILE.cpi2 = 1600
    FACTORY_PROFILE.polling_rate = 1000

    def __init__(self, hid_id=RIVAL_HID_ID, dev_path=None):
        """
        Constructor. It needs a HIDRaw device for initialization.
        """
        device = open_hiddevice(hid_id, dev_path)
        self.__device = device
        self.__profile = Rival.FACTORY_PROFILE

    def send(self, report):
        """
        Send a report packet to the device.
        """
        self.__device.sendFeatureReport(report)

    def _parse_led_color(self, led, color):
        if led not in (LED_LOGO, LED_WHEEL):
            raise ValueError("Invalid LED: %s" % (led,))
        if is_strtype(color):
            try:
                color = webcolors.name_to_rgb(color)
            except ValueError:
                try:
                    color = webcolors.hex_to_rgb(color)
                except ValueError:
                    color = webcolors.hex_to_rgb("#" + color)
        if not hasattr(color, '__iter__'):
            raise ValueError("Invalid Color: %s" % (color, ))
        return color

    def set_led_color(self, led, color):
        color = self._parse_led_color(led, color)
        # Para el Rival ¿300?
        args = (chr(led),) + tuple([chr(int(b)) for b in color])
        return "\x08%s%s%s%s" % args

    def set_led_style(self, led, style):
        if led not in (LED_LOGO, LED_WHEEL):
            raise ValueError("Invalid LED: %s" % (led,))
        if 1 <= style <= 4:
            return '\x07%s%s' % (chr(led), chr(style))
        raise ValueError(
            "Invalid Style %s, valid values are 1, 2, 3 and 4" % (style,))

    def set_wheel_color(self, color):
        return self.set_led_color(LED_WHEEL, color)

    def set_logo_color(self, color):
        return self.set_led_color(LED_LOGO, color)

    def set_wheel_style(self, style):
        return self.set_led_style(LED_WHEEL, style)

    def set_logo_style(self, style):
        return self.set_led_style(LED_LOGO, style)

    def set_cpi(self, cpinum, value):
        if cpinum not in (1, 2):
            raise ValueError("Invalid CPI Number: %s" % (cpinum,))
        if value % 50:
            raise ValueError("CPI Must be increments of 50")
        if not (50 <= value <= 6500):
            raise ValueError("CPI Must be between 50 and 6500")
        return '\x03%s%s' % (chr(cpinum), chr(value / 50))

    def set_cpi_1(self, value):
        return self.set_cpi(1, value)

    def set_cpi_2(self, value):
        return self.set_cpi(2, value)

    def set_polling_rate(self, rate):
        if rate == 1000:
            b = '\x01'
        elif rate == 500:
            b = '\x02'
        elif rate == 250:
            b = '\x03'
        elif rate == 125:
            b = '\x04'
        else:
            raise ValueError("Invalid Polling Rate, valid values are 1000,"
                             " 500, 250 and 125")
        return "\x04\x00%s" % (b,)

    def commit(self):
        return '\x09'


class Rival100(Rival):
    """
    Implements Rival100 protocol. Sighlty different from other Rival mice.
    """
    FACTORY_PROFILE = Profile()
    FACTORY_PROFILE.logo_color = (255, 24, 0)
    FACTORY_PROFILE.wheel_color = (255, 24, 0)
    FACTORY_PROFILE.logo_style = 2
    FACTORY_PROFILE.wheel_style = 2
    FACTORY_PROFILE.cpi1 = 1000
    FACTORY_PROFILE.cpi2 = 2000
    FACTORY_PROFILE.polling_rate = 1000

    def __init__(self, hid_id=RIVAL100_HID_ID, dev_path=None):
        """
        Constructor. It needs a HIDRaw device for initialization.
        """
        Rival.__init__(self, hid_id, dev_path)
        device = open_hiddevice(hid_id, dev_path)
        self.__device = device
        self.__profile = Rival100.FACTORY_PROFILE

    def set_led_color(self, led, color):
        color = self._parse_led_color(led, color)
        # Para el rival 100
        args = tuple([chr(int(b)) for b in color])
        # Wheel and logo color cannot be set separately.
        # «led» is always \x00
        return ("\x05\x00%s%s%s" + (27 * "\x00")) % args
