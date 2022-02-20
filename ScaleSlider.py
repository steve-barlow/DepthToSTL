# ******************************************************************************
# Project : DepthToSTL
# Python 3 program
# Copyright (c) 2016-2022 Steve Barlow
# ******************************************************************************

"""A Qt slider widget supporting float values with a numeric scale above it.

All methods are the same as for QSlider but take floats as well as integers.
There is an additional method pair setInterval() / interval() which defines the
float slider step size (which is always 1 in QSlider). setTickInterval() sets
both the slider tick interval and the scale text interval.

Typical usage:

    slider = ScaleSlider(QtCore.Qt.Horizontal, self)
    slider.setRange(0.0, 20.0)
    slider.setInterval(0.1)
    slider.setTickPosition(QtWidgets.QSlider.TicksBothSides)
    slider.setTickInterval(5)
    slider.setTracking(False)
    slider.valueChanged.connect(self.sliderChanged)
"""

# Implementation based on:
# https://stackoverflow.com/questions/42820380/use-float-for-qslider
# https://www.pythonguis.com/tutorials/pyside-creating-your-own-custom-widgets/

from PySide6 import QtCore, QtGui, QtWidgets

class Scale(QtWidgets.QWidget):
    """Scale to go above a QSlider."""

    def __init__(self, parent=None, knobWidth=0):
        super(Scale, self).__init__(parent)
        self.knobWidth = knobWidth
        self.setFixedHeight(10)
        self.setScale(0, 99, -1)

    def setScale(self, minv, maxv, tickInterval):
        self.minv = minv
        self.maxv = maxv
        self.tickInterval = tickInterval
        self.repaint()

    def paintEvent(self, e):
        w = self.size().width()
        qp = QtGui.QPainter()
        qp.begin(self)
        qp.setFont(QtGui.QFont('Arial', 10))
        if self.tickInterval < 0:
            divs = 1
        else:
            divs = round((self.maxv - self.minv) / self.tickInterval)
        for i in range(divs + 1):
            x = self.knobWidth/2 + i * (w-self.knobWidth)/divs
            val = self.minv + i * (self.maxv-self.minv)/divs
            text = f'{val:g}'
            boundingRect = qp.boundingRect(0, 0, 100, 100, QtCore.Qt.AlignCenter, text)
            textWidth = boundingRect.width()
            qp.drawText(x - textWidth/2, 10, text)
        qp.end()

class ScaleSlider(QtWidgets.QWidget):
    """Qt slider widget supporting float values with a numeric scale above it."""

    def __init__(self, orientation, parent=None):
        super(ScaleSlider, self).__init__(parent)
        assert orientation == QtCore.Qt.Orientation.Horizontal, 'Currently only supports horizontal sliders'

        self.layout = QtWidgets.QVBoxLayout()
        self.layout.setSpacing(0)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.scale = Scale(self, knobWidth=24)
        self.slider = QtWidgets.QSlider(orientation, self)
        self.layout.addWidget(self.scale)
        self.layout.addWidget(self.slider)
        self.setLayout(self.layout)

        self.minv = 0
        self.maxv = 99
        self.interval = 1
        self.tickInterval = -1
        self._range_adjusted()

    def __getattr__(self, name):
        if name in self.__dict__:
            return self[name]

        try:
            return getattr(self.slider, name)
        except AttributeError:
            raise AttributeError(
            "'{}' object has no attribute '{}'".format(self.__class__.__name__, name)
            )

    def value(self):
        return self.index * self.interval + self.minv

    def setValue(self, value):
        index = round((value - self.minv) / self.interval)
        return self.slider.setValue(index)

    @property
    def index(self):
        return self.slider.value()

    def setIndex(self, index):
        return self.slider.setValue(index)

    def minimum(self):
        return self.minv

    def setMinimum(self, value):
        self.minv = value
        self._range_adjusted()

    def maximum(self):
        return self.maxv

    def setMaximum(self, value):
        self.maxv = value
        self._range_adjusted()

    def setRange(self, minv, maxv):
        self.minv = minv
        self.maxv = maxv
        self._range_adjusted()

    def interval(self):
        return self.interval

    def setInterval(self, value):
        # To avoid division by zero
        if not value:
            raise ValueError('Interval of zero specified')
        self.interval = value
        self._range_adjusted()

    def tickInterval(self):
        return self.tickInterval

    def setTickInterval(self, value):
        self.tickInterval = value
        self._range_adjusted()

    def _range_adjusted(self):
        r = self.maxv - self.minv
        number_of_steps = int(r / self.interval)
        self.slider.setMaximum(number_of_steps)
        if self.tickInterval < 0:
            self.slider.setTickInterval(-1)
        else:
            self.slider.setTickInterval(int(self.tickInterval / r * number_of_steps))
        self.scale.setScale(self.minv, self.maxv, self.tickInterval)
