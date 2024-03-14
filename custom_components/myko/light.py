"""Platform for light integration."""
from __future__ import annotations

import logging

from .myko import Myko
import voluptuous as vol

# Import the device class from the component that you want to support
from homeassistant.helpers import config_validation as cv, entity_platform, service
from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    ATTR_RGB_COLOR,
    ATTR_WHITE,
    ATTR_COLOR_TEMP,
    PLATFORM_SCHEMA,
    ColorMode,
    COLOR_MODES_COLOR,
    LightEntity,
)
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType
from datetime import timedelta

# Import exceptions from the requests module
import requests.exceptions

SCAN_INTERVAL = timedelta(seconds=60)
BASE_INTERVAL = timedelta(seconds=60)
SERVICE_NAME = "send_command"
_LOGGER = logging.getLogger(__name__)

CONF_DEBUG: Final = "debug"

# Validation of the user's configuration
PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend(
    {
        vol.Required(CONF_USERNAME): cv.string,
        vol.Required(CONF_PASSWORD): cv.string,
        vol.Required(CONF_DEBUG, default=False): cv.boolean,
    }
)


def _brightness_to_hass(value):
    if value is None:
        value = 0
    return int(value) * 255 // 100


def _brightness_to_myko(value):
    return value * 100 // 255


def _convert_color_temp(value):
    if isinstance(value, str) and value.endswith("K"):
        value = value[:-1]
    if value is None:
        value = 1
    return 1000000 // int(value)


def setup_platform(
    hass: HomeAssistant,
    config: ConfigType,
    add_entities: AddEntitiesCallback,
    discovery_info: DiscoveryInfoType | None = None,
) -> None:
    """Set up the Awesome Light platform."""

    # Assign configuration variables.
    # The configuration check takes care they are present.

    username = config[CONF_USERNAME]
    password = config.get(CONF_PASSWORD)
    debug = config.get(CONF_DEBUG)
    try:
        myko = Myko(username, password)
    except requests.exceptions.ReadTimeout as ex:
        raise PlatformNotReady(
            f"Connection error while connecting to myko: {ex}"
        ) from ex

    entities = []
    _LOGGER.debug("Attempting automatic discovery")
    for [
        childId,
        model,
        deviceId,
        deviceClass,
        friendlyName,
        functions,
    ] in myko.discoverDeviceIds():
        _LOGGER.debug("childId " + childId)
        _LOGGER.debug("Switch on Model " + model)
        _LOGGER.debug("deviceId: " + deviceId)
        _LOGGER.debug("deviceClass: " + deviceClass)
        _LOGGER.debug("friendlyName: " + friendlyName)
        _LOGGER.debug("functions: " + str(functions))

        if deviceClass == "light":
            entities.append(
                MykoLight(
                    myko,
                    friendlyName,
                    debug,
                    childId,
                    model,
                    deviceId,
                    deviceClass,
                    functions,
                )
            )
    if not entities:
        return
    add_entities(entities)

    def my_service(call: ServiceCall) -> None:
        """My first service."""
        _LOGGER.info("Received data" + str(call.data))
        name = SERVICE_NAME
        entity_ids = call.data["entity_id"]
        functionClass = call.data["functionClass"]
        value = call.data["value"]

        if "functionInstance" in call.data:
            functionInstance = call.data["functionInstance"]
        else:
            functionInstance = None

        for entity_id in entity_ids:
            _LOGGER.info("entity_id: " + str(entity_id))
            for i in entities:
                if i.entity_id == entity_id:
                    _LOGGER.info("Found Entity")
                    i.send_command(functionClass, value, functionInstance)

    # Register our service with Home Assistant.
    hass.services.register("myko", "send_command", my_service)


class MykoLight(LightEntity):
    """Representation of an Awesome Light."""

    def __init__(
        self,
        myko,
        friendlyname,
        debug,
        childId=None,
        model=None,
        deviceId=None,
        deviceClass=None,
        functions=None,
    ) -> None:
        """Initialize an AwesomeLight."""

        _LOGGER.debug("Light Name: ")
        _LOGGER.debug(friendlyname)
        self._name = friendlyname

        self._debug = debug
        self._state = "off"
        self._childId = childId
        self._model = model
        self._brightness = None
        self._usePowerFunctionInstance = None
        self._myko = myko
        self._deviceId = deviceId
        self._debugInfo = None

        # colorMode == 'color' || 'white'
        self._colorMode = None
        self._colorTemp = None
        self._min_mireds = None
        self._max_mireds = None
        self._rgbColor = None
        self._temperature_choices = None
        self._temperature_suffix = None
        if None in (childId, model, deviceId, deviceClass) or "" in (childId, model, deviceId, deviceClass):
            [
                self._childId,
                self._model,
                self._deviceId,
                deviceClass,
            ] = self._myko.getChildId(self._name)
        if functions is None:
            functions = self._myko.getFunctions(self._childId)

        self._supported_color_modes = []

        # https://www.castorama.pl/panel-led-goodhome-smart-4600-lm-120-x-30-cm/5063022065582_CAPL.prd
        if  deviceClass == "light" and self._model == "TBD":
            self._supported_color_modes.extend(
                [ColorMode.RGB, ColorMode.COLOR_TEMP, ColorMode.WHITE]
            )
            self._max_mireds = 370
            self._min_mireds = 154


    async def async_setup_entry(hass, entry):
        """Set up the media player platform for Sonos."""

        platform = entity_platform.async_get_current_platform()

        platform.async_register_entity_service(
            "send_command",
            {
                vol.Required("functionClass"): cv.string,
                vol.Required("value"): cv.string,
                vol.Optional("functionInstance"): cv.string,
            },
            "send_command",
        )

    @property
    def name(self) -> str:
        """Return the display name of this light."""
        return self._name

    @property
    def unique_id(self) -> str:
        """Return the display name of this light."""
        return self._childId

    @property
    def color_mode(self) -> ColorMode:
        if self._colorMode == "color":
            return ColorMode.RGB
        return self._colorMode

    @property
    def supported_color_modes(self) -> set[ColorMode]:
        """Flag supported color modes."""
        return {*self._supported_color_modes}

    @property
    def brightness(self) -> int or None:
        """Return the brightness of this light between 0..255."""
        return self._brightness

    @property
    def color_temp(self) -> int | None:
        """Return the CT color value in mireds."""
        return _convert_color_temp(self._color_temp)

    @property
    def min_mireds(self) -> int or None:
        """Return the coldest color_temp that this light supports."""
        return self._min_mireds

    @property
    def max_mireds(self) -> int or None:
        """Return the warmest color_temp that this light supports."""
        return self._max_mireds

    @property
    def is_on(self) -> bool | None:
        """Return true if light is on."""
        if self._state is None:
            return None
        else:
            return self._state == "on"

    def send_command(self, field_name, field_state, functionInstance=None) -> None:
        self._myko.setState(self._childId, field_name, field_state, functionInstance)

    def turn_on(self, **kwargs: Any) -> None:
        state = self._myko.setPowerState(
            self._childId, "on", self._usePowerFunctionInstance
        )

        if ATTR_BRIGHTNESS in kwargs and (
            ColorMode.ONOFF not in self._supported_color_modes
        ):
            brightness = kwargs.get(ATTR_BRIGHTNESS, self._brightness)
            self._myko.setState(
                self._childId, "brightness", _brightness_to_myko(brightness)
            )

        if ATTR_RGB_COLOR in kwargs and any(
            mode in COLOR_MODES_COLOR for mode in self._supported_color_modes
        ):
            self._myko.setRGB(self._childId, *kwargs[ATTR_RGB_COLOR])

        if ATTR_WHITE in kwargs and (
            any(mode in COLOR_MODES_COLOR for mode in self._supported_color_modes)
            or ColorMode.COLOR_TEMP in self._supported_color_modes
        ):
            self._colorMode = ATTR_WHITE
            self._myko.setState(self._childId, "color-mode", self._colorMode)
            brightness = kwargs.get(ATTR_WHITE, self._brightness)
            self._myko.setState(
                self._childId, "brightness", _brightness_to_myko(brightness)
            )

        if ATTR_COLOR_TEMP in kwargs and (
            any(mode in COLOR_MODES_COLOR for mode in self._supported_color_modes)
            or ColorMode.COLOR_TEMP in self._supported_color_modes
        ):
            self._color_temp = _convert_color_temp(kwargs[ATTR_COLOR_TEMP])
            if self._temperature_choices is not None:
                self._color_temp = self._temperature_choices[
                    min(
                        range(len(self._temperature_choices)),
                        key=lambda i: abs(
                            self._temperature_choices[i] - self._color_temp
                        ),
                    )
                ]
            if self._temperature_suffix is not None:
                self._myko.setState(
                    self._childId,
                    "color-temperature",
                    str(self._color_temp) + self._temperature_suffix,
                )
            else:
                self._myko.setState(self._childId, "color-temperature", self._color_temp)

    @property
    def rgb_color(self):
        """Return the rgb value."""
        return self._rgbColor

    @property
    def extra_state_attributes(self):
        """Return the state attributes."""
        attr = {}
        attr["model"] = self._model
        attr["deviceId"] = self._deviceId
        attr["devbranch"] = False

        attr["debugInfo"] = self._debugInfo

        return attr

    def turn_off(self, **kwargs: Any) -> None:
        """Instruct the light to turn off."""
        state = self._myko.setPowerState(
            self._childId, "off", self._usePowerFunctionInstance
        )

    @property
    def should_poll(self):
        """Turn on polling"""
        return True
