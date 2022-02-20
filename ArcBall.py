# ******************************************************************************
# Project : DepthToSTL
# Python 3 program
# Copyright (c) 2016-2022 Steve Barlow
# ******************************************************************************

"""Simple Arcball rotation support for PyOpenGL.

An intuitive way of rotating an object with the mouse. Defined in paper
https://www.talisman.org/~erlkonig/misc/shoemake92-arcball.pdf. Also includes
extension by Gavin Bell which makes it more intuitive for mouse clicks outside
the rotation sphere, by using a projection surface which is a hybrid of a
hemisphere and a hyperbolic sheet.

To use:
import ArcBall

In initialisation:
    a = ArcBall.ArcBallT()
    rot = ArcBall.initialRot(ArcBall.initialViewUnrotated)

In paintGL:
    glMultMatrixf(rot)

In resizeGL:
    a.setBounds(w, h)

On mousedown:
    a.click(rot, x, y)

On drag:
    rot = a.drag(x, y)
"""

# Implementation based on:
# http://pydoc.net/Python/PyOpenGL-Demo/3.0.0/PyOpenGL-Demo.NeHe.lesson48.ArcBall/
# http://www.raywenderlich.com/12667/how-to-rotate-a-3d-object-using-touches-with-opengl
# http://www.opensource.apple.com/source/X11libs/X11libs-60/mesa/Mesa-7.8.2/progs/util/trackball.c

import numpy as np
import math

EPSILON = 1.0e-5
USE_GAVIN_BELL_EXTENSION = True


# ---------------------------------------------------------------------------------------
# Vector / matrix primitives

def vector3f(x=0.0, y=0.0, z=0.0):
    return np.array((x, y, z), 'f')

def quat4f(x=0.0, y=0.0, z=0.0, w=0.0):
    return np.array((x, y, z, w), 'f')

def matrix4f(m=None):
    if m == None:
        return np.identity(4, 'f')
    else:
        return np.array(m, 'f').reshape((4,4))

def mag(v):
    return np.linalg.norm(v)

def normalise(v):
    return v / mag(v)

def matrix4fSetRotationFromQuat4f(q):
    """Converts the H quaternion q into a new equivalent 4x4 rotation matrix."""

    # This math all comes about by way of algebra, complex math, and trig identities
    # See Lengyel pages 88-92

    X = 0; Y = 1; Z = 2; W = 3

    n = np.dot(q, q)
    s = 0.0
    if (n > 0.0):
        s = 2.0 / n

    xs = q[X] * s;  ys = q[Y] * s;  zs = q[Z] * s
    wx = q[W] * xs; wy = q[W] * ys; wz = q[W] * zs
    xx = q[X] * xs; xy = q[X] * ys; xz = q[X] * zs
    yy = q[Y] * ys; yz = q[Y] * zs; zz = q[Z] * zs

    m = matrix4f([[1.0 - (yy + zz), xy + wz,         xz - wy,         0.0],
                  [xy - wz,         1.0 - (xx + zz), yz + wx,         0.0],
                  [xz + wy,         yz - wx,         1.0 - (xx + yy), 0.0],
                  [0.0,             0.0,             0.0,             1.0]])

    return m


# ---------------------------------------------------------------------------------------
# ArcBallT class

class ArcBallT:
    """Class providing methods to map mouse activity to rotation matrix changes."""
    
    def __init__(self):
        self.m_StVec = vector3f()
        self.m_EnVec = vector3f()
        self.m_WindowWidth = 1.0
        self.m_WindowHeight = 1.0

    def __str__(self):
        strRep = ''
        strRep += 'StVec = ' + str (self.m_StVec)
        strRep += '\nEnVec = ' + str (self.m_EnVec)
        strRep += '\nWindow = %f %f' % (self.m_WindowWidth, self.m_WindowHeight)
        return strRep

    def setBounds(self, newWidth, newHeight):
        """Set size of window that mouse is being moved/dragged in."""
        self.m_WindowWidth = newWidth
        self.m_WindowHeight = newHeight

    def _mapToSphere(self, x, y):
        # Return (x,y,z) vector for position of touch point on sphere
        
        # Calculate mouse coords from centre
        cx = (self.m_WindowWidth - 1.0) * 0.5
        cy = (self.m_WindowHeight - 1.0) * 0.5
        sx = x - cx
        sy = cy - y
        minDim = min(self.m_WindowWidth, self.m_WindowHeight) / 2.0

        # Compute the length of the vector to the point from the centre
        length2 = sx*sx + sy*sy
        length = math.sqrt(length2)

        if USE_GAVIN_BELL_EXTENSION:

            # Radius of our arc ball - 0.5 of smallest screen dimension from centre
            radius = 0.5 * minDim
            radius2 = radius * radius

            if length < radius / math.sqrt(2.0):
                # It's on the sphere. Calculate Z
                spherePos = vector3f(sx, sy, math.sqrt(radius2 - length2))
            else: 
                # The point is outside of the sphere. Use the hyperbola
                pz = radius2 / (2.0 * length)
                spherePos = vector3f(sx, sy, pz)

        else: # Standard ArcBall

            # Radius of our arc ball - 0.7 of smallest screen dimension from centre
            radius = 0.7 * minDim
            radius2 = radius * radius

            if length < radius:
                # It's on the sphere. Calculate Z
                spherePos = vector3f(sx, sy, math.sqrt(radius2 - length2))
            else: 
                # The point is outside of the sphere. Clamp to Z=0 great circle
                spherePos = vector3f(sx, sy, 0.0)

        # Normalise
        spherePos = normalise(spherePos)
        return spherePos

    def click (self, startRot, x, y):
        """Respond to mouse down."""
        self.startRot = np.copy(startRot)
        self.m_StVec = self._mapToSphere(x, y)
        return

    def drag (self, x, y):
        """Respond to mouse drag, calculate rotation."""
        X = 0; Y = 1; Z = 2; W = 3

        self.m_EnVec = self._mapToSphere(x, y)

        # Compute the vector perpendicular to the begin and end vectors
        perp = np.cross(self.m_StVec, self.m_EnVec)

        # Compute the length of the perpendicular vector
        if mag(perp) > EPSILON:
            # We're ok, so return the perpendicular vector as the transform
            quat = quat4f()
            quat[X] = perp[X]
            quat[Y] = perp[Y]
            quat[Z] = perp[Z]
            # In the quaternion values, W is cos(theta/2), where theta is rotation angle
            quat[W] = np.dot(self.m_StVec, self.m_EnVec)
        else:
            # The begin and end vectors coincide, so return a quaternion of zeroes (no rotation)
            quat = quat4f()
            
        r = matrix4fSetRotationFromQuat4f(quat)
        # Linear Algebra matrix multiplication A = old, B = New : C = A * B
        # np.dot does matrix multiplication when given an array rather than a vector
        return np.dot(self.startRot, r)
    
# Quaternion initial rotation choices
initialViewUnrotated = quat4f(0.0, 0.0, 0.0, 0.0)
initialViewY = quat4f(-math.sqrt(2.0), 0.0, 0.0, math.sqrt(2.0))

def initialRot(q=initialViewUnrotated):
    """Return a 4x4 matrix defining an initial rotation.

    Can set different initial rotation values by giving a quaternion argument. Can use canned
    values for these: initialViewUnrotated or initialViewY.
    """
    return matrix4fSetRotationFromQuat4f(q)
