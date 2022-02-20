#!/usr/bin/env python
# ******************************************************************************
# Project : DepthToSTL
# Python 3 program
# Copyright (c) 2016-2022 Steve Barlow
# ******************************************************************************

"""Create 3D model from greyscale depth map image, with facility to view and output to STL file."""

VER = '0.3.0'

import sys
import os
from PySide6 import QtCore, QtGui, QtWidgets, QtOpenGLWidgets
from OpenGL.GL import *
from OpenGL.GLU import *
import OpenGL_accelerate
from PySide6.QtOpenGL import *
import numpy as np
import cv2 as cv
import ArcBall
import ScaleSlider

# Draw X,Y,Z axes
DRAW_AXES = True


# ---------------------------------------------------------------------------------------
# DepthMapModel model

class DepthMapModel:
    """Object for holding/manipulating a depth map."""

    def __init__(self):
        self.depthMap = None

    def setDepthMap(self, depthMap, name):
        """depthMap is a greyscale image with pixels between 0.0 and 1.0."""
        self.depthMap = np.flipud(depthMap) # flip because OpenGL measures Y upwards
        self.name = name

        h, w = self.depthMap.shape
        scaleFactor = 1.0 / max(h-1, w-1)
        self.xcentre = (w-1) * scaleFactor / 2.0
        self.ycentre = (h-1) * scaleFactor / 2.0
        self.zcentre = np.max(self.depthMap) / 2.0

        def s(a):
            return a * scaleFactor

        nvertices = h*w + 4*(w+h) + 4 # top grid plus sides plus 4 for base
        self.vertices = np.zeros((nvertices, 3))
        self.normals = np.zeros((nvertices, 3))

        def vindex(level, x, y):
            if level == 0: # top
                return y*w + x
            elif level in [1, 2, 3, 4]: # x slides
                return h*w + (level-1)*w + x
            elif level in [5, 6, 7, 8]:
                return h*w + 4*w + (level-5)*h + y # y sides
            else: # bottom
                return h*w + 4*w + 4*h + int(y>0)*2 + int(x>0)

        nquads = (h-1)*(w-1) + 2*(w-1) + 2*(h-1) + 1 # grid plus sides plus 1 for base
        self.indices = np.zeros((nquads, 6), dtype=int)
        self.qindex = 0

        def addGridQuad(level, x1, y1, x2, y2):
            self.indices[self.qindex] = [vindex(level, x1, y1), vindex(level, x2, y1), vindex(level, x2, y2),
                                        vindex(level, x1, y1), vindex(level, x2, y2), vindex(level, x1, y2)]
            self.qindex += 1
            
        def addSideQuad(level, x1, y1, x2, y2):
            self.indices[self.qindex] = [vindex(level+1, x1, y1), vindex(level+1, x2, y2), vindex(level, x2, y2),
                                        vindex(level+1, x1, y1), vindex(level, x2, y2), vindex(level, x1, y1)]
            self.qindex += 1

        # Top grid
        for y in range(h):
            for x in range(w):
                self.vertices[vindex(0, x, y)] = [s(x), s(y), self.depthMap[y, x]]
                nx = ny = dx = dy = 0.0
                if x > 0: nx += 1.0; dx += self.depthMap[y,x] - self.depthMap[y,x-1]
                if x < w-1: nx += 1.0; dx += self.depthMap[y,x+1] - self.depthMap[y,x]
                if y > 0: ny += 1.0; dy += self.depthMap[y,x] - self.depthMap[y-1,x]
                if y < h-1: ny += 1.0; dy += self.depthMap[y+1,x] - self.depthMap[y,x]
                p1 = [0.0, 0.0, 0.0]
                p2 = [s(nx), 0.0, dx]
                p3 = [0.0, s(ny), dy]
                self.normals[vindex(0, x, y)] = self._normal(p1, p2, p3)
        for y in range(h-1):
            for x in range(w-1):
                addGridQuad(0, x, y, x+1, y+1)

        # Sides
        for x in range(w):
            self.vertices[vindex(1, x, 0)] = [s(x), s(0), self.depthMap[0,x]]
            self.normals[ vindex(1, x, 0)] = [0.0, -1.0, 0.0]
            self.vertices[vindex(2, x, 0)] = [s(x), s(0), 0.0]
            self.normals[ vindex(2, x, 0)] = [0.0, -1.0, 0.0]
            self.vertices[vindex(3, x, h-1)] = [s(x), s(h-1), self.depthMap[h-1,x]]
            self.normals[ vindex(3, x, h-1)] = [0.0, 1.0, 0.0]
            self.vertices[vindex(4, x, h-1)] = [s(x), s(h-1), 0.0]
            self.normals[ vindex(4, x, h-1)] = [0.0, 1.0, 0.0]
            if x < w-1:
                addSideQuad(1, x, 0, x+1, 0)
                addSideQuad(3, x+1, h-1, x, h-1)                        
        for y in range(h):
            self.vertices[vindex(5, 0, y)] = [s(0), s(y), self.depthMap[y,0]]
            self.normals[ vindex(5, 0, y)] = [-1.0, 0.0, 0.0]
            self.vertices[vindex(6, 0, y)] = [s(0), s(y), 0.0]
            self.normals[ vindex(6, 0, y)] = [-1.0, 0.0, 0.0]
            self.vertices[vindex(7, w-1, y)] = [s(w-1), s(y), self.depthMap[y,w-1]]
            self.normals[ vindex(7, w-1, y)] = [1.0, 0.0, 0.0]
            self.vertices[vindex(8, w-1, y)] = [s(w-1), s(y), 0.0]
            self.normals[ vindex(8, w-1, y)] = [1.0, 0.0, 0.0]
            if y < h-1:
                addSideQuad(5, 0, y+1, 0, y)
                addSideQuad(7, w-1, y, w-1, y+1)                        

        # Base
        self.vertices[vindex(9, 0, 0)] = [s(0), s(0), 0.0]
        self.normals[ vindex(9, 0, 0)] = [0.0, 0.0, -1.0]
        self.vertices[vindex(9, 0, h-1)] = [s(0), s(h-1), 0.0]
        self.normals[ vindex(9, 0, h-1)] = [0.0, 0.0, -1.0]
        self.vertices[vindex(9, w-1, h-1)] = [s(w-1), s(h-1), 0.0]
        self.normals[ vindex(9, w-1, h-1)] = [0.0, 0.0, -1.0]
        self.vertices[vindex(9, w-1, 0)] = [s(w-1), s(0), 0.0]
        self.normals[ vindex(9, w-1, 0)] = [0.0, 0.0, -1.0]
        addGridQuad(9, 0, h-1, w-1, 0)
        
    def draw(self):
        if self.depthMap is not None:
            glPushMatrix()
            glTranslatef(-self.xcentre, -self.ycentre, -self.zcentre)

            # Front is red
            glMaterial(GL_FRONT, GL_AMBIENT, [0.2, 0.05, 0.05, 1.0])
            glMaterial(GL_FRONT, GL_DIFFUSE, [0.4, 0.1, 0.1, 1.0])
            glMaterial(GL_FRONT, GL_SPECULAR, [0.4, 0.1, 0.1, 1.0])
            glMaterial(GL_FRONT, GL_SHININESS, 50.0)

            # Back is grey
            glMaterial(GL_BACK, GL_AMBIENT, [0.2, 0.2, 0.2, 1.0])
            glMaterial(GL_BACK, GL_DIFFUSE, [0.4, 0.4, 0.4, 1.0])
            glMaterial(GL_BACK, GL_SPECULAR, [0.4, 0.4, 0.4, 1.0])
            glMaterial(GL_BACK, GL_SHININESS, 50.0)

            glEnableClientState(GL_VERTEX_ARRAY)
            glEnableClientState(GL_NORMAL_ARRAY)
            
            glVertexPointer(3, GL_DOUBLE, 0, self.vertices)
            glNormalPointer(GL_DOUBLE, 0, self.normals)
            glDrawElements(GL_TRIANGLES, self.indices.size, GL_UNSIGNED_INT, self.indices)

            glDisableClientState(GL_VERTEX_ARRAY)
            glDisableClientState(GL_NORMAL_ARRAY)

##            # Debug - draw normals
##            glDisable(GL_LIGHTING)
##            glColor3f(1.0, 0.0, 1.0)
##            for v,n in zip(self.vertices, self.normals):
##                glBegin(GL_LINES)
##                glVertex3f(*v)
##                glVertex3f(*(v+n/8.0))
##                glEnd()
##            glColor3f(1.0, 1.0, 1.0)
##            glEnable(GL_LIGHTING)

            glPopMatrix()

    def _normal(self, p1, p2, p3):
        # Calculate unit normal vector for triangle of 3 points p1, p2, p3 in that winding order
        d1 = np.subtract(p2, p1)
        d2 = np.subtract(p3, p1)
        n = np.cross(d1, d2)
        mag = np.linalg.norm(n)
        if mag != 0:
            n /= mag
        return n

    def saveAsSTLFile(self, filename):
        if self.depthMap is not None:
            def emit_triangle(f, p1, p2, p3):
                n = self._normal(p1, p2, p3)
                print(f'facet normal {n[0]:e} {n[1]:e} {n[2]:e}', file=f)
                print(f'    outer loop', file=f)
                print(f'        vertex {p1[0]:e} {p1[1]:e} {p1[2]:e}', file=f)
                print(f'        vertex {p2[0]:e} {p2[1]:e} {p2[2]:e}', file=f)
                print(f'        vertex {p3[0]:e} {p3[1]:e} {p3[2]:e}', file=f)
                print(f'    endloop', file=f)
                print(f'endfacet', file=f)
                
            with open(filename, 'wt') as f:
                safeName = self.name.replace(' ', '_')
                print(f'solid {safeName}', file=f)
                nquads = self.indices.shape[0]
                for i in range(nquads):
                    p1 = self.vertices[self.indices[i][0]]
                    p2 = self.vertices[self.indices[i][1]]
                    p3 = self.vertices[self.indices[i][2]]
                    emit_triangle(f, p1, p2, p3)
                    p1 = self.vertices[self.indices[i][3]]
                    p2 = self.vertices[self.indices[i][4]]
                    p3 = self.vertices[self.indices[i][5]]
                    emit_triangle(f, p1, p2, p3)
                print(f'endsolid {safeName}', file=f)

        
# ---------------------------------------------------------------------------------------
# MyGL widget

class MyGLWidget(QtOpenGLWidgets.QOpenGLWidget):
    
    def __init__(self, model, parent):
        super(MyGLWidget, self).__init__(parent)
        self.setFocusPolicy(QtCore.Qt.StrongFocus)
        self.model = model
        self.arcBall = ArcBall.ArcBallT()
        self.rot = ArcBall.initialRot(ArcBall.initialViewY)

    def paintGL(self):
        glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
        glLoadIdentity()
        glTranslatef(0.0, 0.0, -3.0)
        glMultMatrixf(self.rot)

        self.model.draw()
        if DRAW_AXES:
            self.drawAxes()

    def resizeGL(self, w, h):
        glViewport(0, 0, w, h)
        glMatrixMode(GL_PROJECTION)
        glLoadIdentity()
        aspectRatio = float(w)/h
        gluPerspective(30, aspectRatio, 0.1, 1000.0)
        glMatrixMode(GL_MODELVIEW)
        self.arcBall.setBounds(w, h)

    def initializeGL(self):
        glClearColor(0.4, 0.4, 0.4, 1.0)
        glEnable(GL_DEPTH_TEST)
        glLightModelf(GL_LIGHT_MODEL_TWO_SIDE, 1.0)

        # Uncomment this line for a wireframe view
        # glPolygonMode(GL_FRONT_AND_BACK, GL_LINE)

        glLight(GL_LIGHT0, GL_AMBIENT, [1.0, 1.0, 1.0, 1.0])
        glLight(GL_LIGHT0, GL_DIFFUSE, [1.0, 1.0, 1.0, 1.0])
        glLight(GL_LIGHT0, GL_SPECULAR, [1.0, 1.0, 1.0, 1.0])
        glLight(GL_LIGHT0, GL_POSITION, [0.0, 0.0, 10.0, 0.0])
        glLight(GL_LIGHT1, GL_AMBIENT, [0.5, 0.5, 0.5, 1.0])
        glLight(GL_LIGHT1, GL_DIFFUSE, [0.5, 0.5, 0.5, 1.0])
        glLight(GL_LIGHT1, GL_SPECULAR, [1.0, 1.0, 1.0, 1.0])
        glLight(GL_LIGHT1, GL_POSITION, [-6.0, 6.0, 10.0, 0.0])
        glLightModelfv(GL_LIGHT_MODEL_AMBIENT, [0.2, 0.2, 0.2, 1.0])
        glEnable(GL_LIGHTING)
        glEnable(GL_LIGHT0)
        glEnable(GL_LIGHT1)

    def drawAxes(self):
        # Draw X, Y and Z axes
        glDisable(GL_LIGHTING)
        glColor3f(1.0, 0.0, 0.0)
        glBegin(GL_LINES)
        glVertex3f(-1000.0, 0.0, 0.0)
        glVertex3f(1000.0, 0.0, 0.0)
        glEnd()
        glColor3f(0.0, 1.0, 0.0)
        glBegin(GL_LINES)
        glVertex3f(0.0, -1000.0, 0.0)
        glVertex3f(0.0, 1000.0, 0.0)
        glEnd()
        glColor3f(0.0, 0.0, 1.0)
        glBegin(GL_LINES)
        glVertex3f(0.0, 0.0, -1000.0)
        glVertex3f(0.0, 0.0, 1000.0)
        glEnd()
        glColor3f(1.0, 1.0, 1.0)
        glEnable(GL_LIGHTING)

    def mousePressEvent(self, e):
        # Start drag rotation
        p = e.position()
        self.arcBall.click(self.rot, p.x(), p.y())

    def mouseMoveEvent(self, e):
        # Rotate model by dragging
        p = e.position()
        self.rot = self.arcBall.drag(p.x(), p.y())
        self.update()


# ---------------------------------------------------------------------------------------
# Main window

class MainWindow(QtWidgets.QWidget):
    
    def __init__(self):
        super(MainWindow, self).__init__()
        self._initUI()
        
    def _initUI(self):
        self.hbox = QtWidgets.QHBoxLayout()

        self.vbox = QtWidgets.QVBoxLayout()
        self.hbox.addLayout(self.vbox)
        self.hbox.addSpacing(10)

        self.model = DepthMapModel()
        self.view = MyGLWidget(self.model, self)
        self.hbox.addWidget(self.view, stretch=1)

        # Contents of controls vbox

        self.depthMap = None
        self.openbtn = QtWidgets.QPushButton('Open Depth Map...', self)
        self.openbtn.clicked.connect(self._openDepthMap)
        self.filelabel = QtWidgets.QLabel('File: None', self)
        self.filelabel.setFixedWidth(280)
        self.imagelabel = QtWidgets.QLabel(self)
        self.imagelabel.setFixedSize(280,190)
        self.imagelabel.setFrameShape(QtWidgets.QFrame.Box)
        self.reslabel = QtWidgets.QLabel('Size:', self)

        self.rlabel = QtWidgets.QLabel('Resolution', self)
        self.rspinbox = QtWidgets.QDoubleSpinBox(self)
        self.rspinbox.setRange(0.10, 2.0)
        self.rspinbox.setSingleStep(0.01)
        self.rspinbox.setSuffix('x')
        self.rspinbox.setValue(1.0)
        self.rspinbox.valueChanged.connect(self._resolutionChanged)
        
        self.slabel = QtWidgets.QLabel('Smoothing', self)
        self.sslider = ScaleSlider.ScaleSlider(QtCore.Qt.Horizontal, self)
        self.sslider.setRange(0, 20)
        self.sslider.setInterval(0.1)
        self.sslider.setTickPosition(QtWidgets.QSlider.TicksBothSides)
        self.sslider.setTickInterval(5)
        self.sslider.setTracking(False)
        self.sslider.valueChanged.connect(self._ssliderChanged)

        self.tlabel = QtWidgets.QLabel('Transform. z = f(p) e.g.', self)
        self.texamplebox = QtWidgets.QHBoxLayout()
        self.examplefont = QtGui.QFont('Arial', 10)
        texample1Text = \
            '    p + 0.2\n' + \
            '    1.0 - p\n' + \
            '    np.clip(p, 0.2, 0.5)\n' + \
            '    p + x/5.0\n' + \
            '    0.1 * np.sin(10*x) + 0.5'
        self.texample1 = QtWidgets.QLabel(texample1Text, self)
        self.texample1.setFont(self.examplefont)
        texample2Text = \
            'Add pedestal\n' + \
            'Black is higher\n' + \
            'Clip Z value\n' + \
            'Add slope\n' + \
            'Draw graph'
        self.texample2 = QtWidgets.QLabel(texample2Text, self)
        self.texample2.setFont(self.examplefont)
        self.texamplebox.addWidget(self.texample1)
        self.texamplebox.addWidget(self.texample2)
        self.tlineedit = QtWidgets.QLineEdit(self)
        self._transformSetText('p')
        self.tlineedit.editingFinished.connect(self._transformChangedPrefilter)
        self.terrorlabel = QtWidgets.QLabel(self)
        self.terrorlabel.setStyleSheet("QLabel { color : red; }")

        self.savebtn = QtWidgets.QPushButton('Save as STL File...', self)
        self.savebtn.clicked.connect(self._saveAsSTLFile)

        self.vbox.addWidget(self.openbtn)
        self.vbox.addWidget(self.filelabel)
        self.vbox.addWidget(self.imagelabel)
        self.vbox.addWidget(self.reslabel)
        self.vbox.addSpacing(10)
        self.vbox.addWidget(self.rlabel)
        self.vbox.addWidget(self.rspinbox)
        self.vbox.addSpacing(10)
        self.vbox.addWidget(self.slabel)
        self.vbox.addWidget(self.sslider)
        self.vbox.addSpacing(10)
        self.vbox.addWidget(self.tlabel)
        self.vbox.addLayout(self.texamplebox)
        self.vbox.addWidget(self.tlineedit)
        self.vbox.addWidget(self.terrorlabel)
        self.vbox.addSpacing(10)
        self.vbox.addWidget(self.savebtn)
        self.vbox.addStretch(1)

        self.setLayout(self.hbox)    
        
        self.setGeometry(300, 300, 910, 610)
        self.setWindowTitle('DepthToSTL V{0}'.format(VER))
        self.show()

    def _openDepthMap(self):
        filename, _ = QtWidgets.QFileDialog.getOpenFileName(self, 'Open Depth Map', '', 'Image (*.png *.jpg *.bmp)')
        if filename != '': # User didn't press Cancel
            basename = os.path.basename(filename)
            self.name = os.path.splitext(basename)[0]
            self.filelabel.setText('File: ' + basename)
            pixmap = QtGui.QPixmap(filename).scaled(280, 190, QtCore.Qt.KeepAspectRatio)
            self.imagelabel.setFixedSize(pixmap.size())
            self.imagelabel.setPixmap(pixmap)
            depthMap = cv.imread(filename, cv.IMREAD_GRAYSCALE)
            # Add a tiny pedestal to this 0..255 image, so black doesn't produce nothing
            h, w = depthMap.shape
            self.reslabel.setText('Size: {0} x {1}'.format(w, h))
            # Reset resolution, smoothing and transform settings
            # Set self.depthMap to None during this so 'Changed' functions that will be triggered don't do anything
            self.depthMap = None
            maxhw = max(w, h)
            if maxhw > 300:
                initialResolution = 300.0 / maxhw
            else:
                initialResolution = 1.0
            self.rspinbox.setValue(initialResolution)
            self.sslider.setValue(0.0)
            self._transformSetText('p')
            self.depthMap = depthMap
            # Update the GUI before potential long processing
            QtWidgets.QApplication.processEvents()
            self._resolutionChanged()

    def _resolutionChanged(self):
        if self.depthMap is not None:
            f = self.rspinbox.value()
            self.resizedDepthMap = cv.resize(self.depthMap, (0,0), fx=f, fy=f)
            self._ssliderChanged()
        
    def _ssliderChanged(self):
        if self.depthMap is not None:
            sigma = max(self.sslider.value(), 0.01)
            self.smoothedDepthMap = cv.GaussianBlur(self.resizedDepthMap, (0,0), sigma)
            self._transformChanged()

    def _transformSetText(self, newVal):
        # Replacement for self.tlineedit.setText that locally records new value
        self.ttext = newVal
        self.tlineedit.setText(newVal)
        
    def _transformChangedPrefilter(self):
        # Filter changes to only propagate them if the text has actually changed, not just a loss of focus
        # This is needed because _transformChanged() can take a long time to execute
        newVal = self.tlineedit.text()
        if newVal != self.ttext:
            self.ttext = newVal
            self._transformChanged()
        
    def _transformChanged(self):
        if self.depthMap is not None:
            try:
                # Create useful values to be used in transform p[], h, w, x[], y[]
                p = self.smoothedDepthMap / 255.0
                # Add a tiny pedestal so black pixels don't produce nothing
                p += 1E-4
                h, w = p.shape
                maxhw =  max(h, w)
                sx = float(w) / maxhw
                sy = float(h) / maxhw
                x = np.zeros_like(p)
                x[:] = np.linspace(-sx, sx, w)
                y = np.zeros_like(p)
                y[:] = np.linspace(sy, -sy, h).reshape((h,1)) # N.B. top of image is +1
                # Apply transform
                transformedDepthMap = eval(str(self.tlineedit.text()))
                transformedDepthMap = np.clip(transformedDepthMap, 0.0, 10.0)
                self.terrorlabel.clear()
            except Exception as e:
                self.terrorlabel.setText(str(e))
                return
            QtWidgets.QApplication.setOverrideCursor(QtCore.Qt.WaitCursor)
            self.model.setDepthMap(transformedDepthMap, self.name)
            self.view.update()
            QtWidgets.QApplication.restoreOverrideCursor()

    def _saveAsSTLFile(self):
        if self.depthMap is not None:
            filename, _ = QtWidgets.QFileDialog.getSaveFileName(self, 'Save as STL File', 'Untitled.stl', 'Stereolithography file (*.stl)')
            if filename != '': # User didn't press Cancel
                self.model.saveAsSTLFile(filename)
       
        
# ---------------------------------------------------------------------------------------
# Main code

def main():

    app = QtWidgets.QApplication(sys.argv)
    path = os.path.join(os.path.dirname(sys.modules[__name__].__file__), 'DepthToSTLIcon.png')
    app.setWindowIcon(QtGui.QIcon(path))
    mainWindow = MainWindow()
    sys.exit(app.exec())


if __name__ == '__main__':
    main()
