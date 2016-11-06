# -*- coding: utf-8 -*-
########################################################################################################################
#
# Copyright (c) 2014, Regents of the University of California
# All rights reserved.
#
# Redistribution and use in source and binary forms, with or without modification, are permitted provided that the
# following conditions are met:
#
# 1. Redistributions of source code must retain the above copyright notice, this list of conditions and the following
#   disclaimer.
# 2. Redistributions in binary form must reproduce the above copyright notice, this list of conditions and the
#    following disclaimer in the documentation and/or other materials provided with the distribution.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES,
# INCLUDING, BUT NOT LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
# DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL,
# SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR
# SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY,
# WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
# OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
#
########################################################################################################################


"""This module defines abstract analog mosfet template classes.
"""

import abc
import numpy as np
from itertools import repeat, chain

from bag import float_to_si_string
from bag.layout.util import BBox
from bag.layout.template import MicroTemplate


class AnalogMosBase(MicroTemplate):
    """An abstract template for analog mosfet.

    Must have parameters mos_type, lch, w, threshold, fg.
    Instantiates a transistor with minimum G/D/S connections.

    Parameters
    ----------
    grid : :class:`bag.layout.routing.RoutingGrid`
            the :class:`~bag.layout.routing.RoutingGrid` instance.
    lib_name : str
        the layout library name.
    params : dict
        the parameter values.
    used_names : set[str]
        a set of already used cell names.
    tech_name : str
        the technology name.
    """
    __metaclass__ = abc.ABCMeta

    def __init__(self, grid, lib_name, params, used_names, tech_name):
        self.tech_name = tech_name
        MicroTemplate.__init__(self, grid, lib_name, params, used_names)

    def get_num_tracks(self):
        """Returns the number of tracks in this template.

        AnalogMosBase should always have at least one track, and the bottom-most track is always
        for gate connection.

        Returns
        -------
        num_track : int
            number of tracks in this template.
        """
        layout_unit = self.grid.get_layout_unit()
        h = self.array_box.height
        tr_w = self.params['track_width'] / layout_unit
        tr_s = self.params['track_space'] / layout_unit
        tr_pitch = tr_w + tr_s

        num_track = int(round(h / tr_pitch))
        if abs(h - num_track * tr_pitch) >= self.grid.get_resolution():
            raise Exception('array box height = %.4g not integer number of track pitch = %.4g' % (h, tr_pitch))
        return num_track

    def get_layout_basename(self):
        """Returns the base name for this template.

        Returns
        -------
        base_name : str
            the base name of this template.
        """

        lch_str = float_to_si_string(self.params['lch'])
        w_str = float_to_si_string(self.params['w'])
        tr_w_str = float_to_si_string(self.params['track_width'])
        tr_s_str = float_to_si_string(self.params['track_space'])
        g_ntr = self.params['g_tracks']
        ds_ntr = self.params['ds_tracks']
        return '%s_%s_%s_l%s_w%s_fg%d_trw%s_trs%s_ng%d_nds%d_base' % (self.tech_name,
                                                                      self.params['mos_type'],
                                                                      self.params['threshold'],
                                                                      lch_str, w_str,
                                                                      self.params['fg'],
                                                                      tr_w_str, tr_s_str,
                                                                      g_ntr, ds_ntr)

    def compute_unique_key(self):
        return self.get_layout_basename()


class AnalogFinfetFoundation(MicroTemplate):
    """The abstract base class for finfet layout classes.

    This class provides the draw_foundation() method, which draws the poly array
    and implantation layers.
    """

    __metaclass__ = abc.ABCMeta

    def __init__(self, grid, lib_name, params, used_names):
        MicroTemplate.__init__(self, grid, lib_name, params, used_names)

    def draw_foundation(self, layout, lch=16e-9, nfin=4, fg=4,
                        nduml=0, ndumr=0, arr_box_ext=None,
                        tech_constants=None):
        """Draw the layout of this template.

        Override this method to create the layout.

        Parameters
        ----------
        layout : :class:`bag.layout.core.BagLayout`
            the BagLayout instance to draw the layout with.
        lch : float
            the transistor channel length.
        nfin : float for int
            array box height in number of fins.
        fg : int
            number of polys to draw.
        nduml : int
            number of dummy polys on the left.
        ndumr : int
            number of dummy polys on the right.
        arr_box_ext : list[float]
            array box extension on the left, bottom, right, and top.
        tech_constants : dict[str, any]
            the technology constants dictionary.  Must have the following entries:

            mos_fin_pitch : float
                the pitch between fins.
            mos_cpo_h : float
                the height of CPO layer.
            sd_pitch : float
                source and drain pitch of the transistor.
            implant_layers : list[str]
                list of implant/threshold layers to draw.
        """
        if arr_box_ext is None:
            arr_box_ext = [0, 0, 0, 0]

        lch /= self.grid.get_layout_unit()
        res = self.grid.get_resolution()

        mos_fin_pitch = tech_constants['mos_fin_pitch']
        mos_cpo_h = tech_constants['mos_cpo_h']
        sd_pitch = tech_constants['sd_pitch']
        lay_list = tech_constants['implant_layers']

        extl, extb, extr, extt = arr_box_ext

        # +2 to account for 2 PODE polys.
        fg_tot = nduml + fg + ndumr
        bnd_box_w = fg_tot * sd_pitch + extl + extr

        # compute array box
        pr_bnd_yext = mos_fin_pitch * (np.ceil(mos_cpo_h / mos_fin_pitch - 0.5) + 0.5)
        arr_box_bot = pr_bnd_yext
        arr_box_top = arr_box_bot + nfin * mos_fin_pitch
        arr_box_left = extl
        arr_box_right = bnd_box_w - extr
        arr_box = BBox(arr_box_left, arr_box_bot, arr_box_right, arr_box_top, res)

        # draw CPO
        layout.add_rect('CPO', BBox(0.0, arr_box.bottom - mos_cpo_h / 2.0,
                                    bnd_box_w, arr_box.bottom + mos_cpo_h / 2.0, res))
        layout.add_rect('CPO', BBox(0.0, arr_box.top - mos_cpo_h / 2.0,
                                    bnd_box_w, arr_box.top + mos_cpo_h / 2.0, res))

        # draw DPO/PO
        dpo_lp = ('PO', 'dummy1')
        po_lp = ('PO', 'drawing')
        for idx, (layer, purpose) in enumerate(chain(repeat(dpo_lp, nduml), repeat(po_lp, fg),
                                                     repeat(dpo_lp, ndumr))):
            xmid = (idx + 0.5) * sd_pitch + extl
            layout.add_rect(layer, BBox(xmid - lch / 2.0, arr_box.bottom - extb,
                                        xmid + lch / 2.0, arr_box.top + extt, res),
                            purpose=purpose)

        # draw VT/implant
        imp_box = BBox(0.0, arr_box.bottom - extb,
                       arr_box.right + extr, arr_box.top + extt, res)
        for lay in lay_list:
            layout.add_rect(lay, imp_box)

        # draw PR boundary
        layout.add_rect('prBoundary', BBox(0.0, 0.0, arr_box_right + extr,
                                           arr_box_top + pr_bnd_yext, res),
                        purpose='boundary')

        # set array box of this template
        self.array_box = arr_box


class AnalogFinfetExt(AnalogFinfetFoundation):
    """The template for finfet vertical extension block.  Used to add more routing tracks.

    Parameters
    ----------
    grid : :class:`bag.layout.routing.RoutingGrid`
            the :class:`~bag.layout.routing.RoutingGrid` instance.
    lib_name : str
        the layout library name.
    params : dict
        the parameter values.
    used_names : set[str]
        a set of already used cell names.
    """

    def __init__(self, grid, lib_name, params, used_names):
        AnalogFinfetFoundation.__init__(self, grid, lib_name, params, used_names)

    def get_default_params(self):
        """Returns the default parameter dictionary.

        Override this method to return a dictionary of default parameter values.
        This returned dictionary should not include port_specs

        Returns
        -------
        default_params : dict[str, any]
            the default parameters dictionary.
        """
        return dict(mos_type='nch',
                    threshold='ulvt',
                    lch=16e-9,
                    nfin=8,
                    fg=2,
                    tech_constants=None,
                    )

    def get_layout_basename(self):
        """Returns the base name for this template.

        Returns
        -------
        base_name : str
            the base name of this template.
        """
        mos_type = self.params['mos_type']
        threshold = self.params['threshold']
        lch = self.params['lch']
        nfin = self.params['nfin']
        fg = self.params['fg']
        tech_str = self.params['tech_constants']['name']
        lch_str = float_to_si_string(lch)
        return '%s_%s_%s_l%s_fin%d_fg%d_ext' % (tech_str, mos_type, threshold, lch_str, nfin, fg)

    def compute_unique_key(self):
        return self.get_layout_basename()

    def draw_layout(self, layout, temp_db,
                    mos_type='nch', threshold='lvt', lch=16e-9,
                    nfin=4, fg=4, tech_constants=None):
        """Draw the layout of this template.

        Override this method to create the layout.

        Parameters
        ----------
        layout : :class:`bag.layout.core.BagLayout`
            the BagLayout instance to draw the layout with.
        temp_db : :class:`bag.layout.template.TemplateDB`
            the TemplateDB instance.  Used to create new templates.
        mos_type : str
            the transistor type.  Either 'nch' or 'pch'
        threshold : str
            the transistor threshold flavor.
        lch : float
            the transistor channel length.
        nfin : float for int
            array box height in number of fins.
        fg : int
            the transistor number of fingers.
        tech_constants : dict[str, any]
            the technology constants dictionary.  Must have the following entries:

            mos_fin_pitch : float
                the pitch between fins.
            mos_cpo_h : float
                the height of CPO layer.
            sd_pitch : float
                source and drain pitch of the transistor.
            implant_layers : list[str]
                list of implant/threshold layers to draw.
            name : str
                a string describing the process technology.  Used for identification purposes.
            mos_edge_num_dpo : int
                number of dummy polys at each edge.
            mos_edge_xext : float
                horizontal extension of CPO/implant layers over the array box left and right edges.
        """

        if fg <= 0:
            raise ValueError('Number of fingers must be positive.')

        nfin_min = tech_constants['mos_ext_nfin_min']

        if nfin < nfin_min:
            raise ValueError('Extension must have a minimum of %d fins' % nfin_min)

        ndum = tech_constants['mos_edge_num_dpo']  # type: int
        xext = tech_constants['mos_edge_xext']  # type: float

        # if we're creating a substrate extension, make sure CPO overlap rule is met
        if mos_type == 'ptap' or mos_type == 'ntap':
            mos_core_cpo_po_ov = tech_constants['mos_core_cpo_po_ov']
            mos_cpo_h = tech_constants['mos_cpo_h']
            extb = max(mos_core_cpo_po_ov - mos_cpo_h / 2.0, 0.0)
        else:
            extb = 0.0

        # include 2 PODE polys
        self.draw_foundation(layout, lch=lch, nfin=nfin, fg=fg + 2,
                             nduml=ndum, ndumr=ndum, arr_box_ext=[xext, extb, xext, 0.0],
                             tech_constants=tech_constants)


class AnalogFinfetEdge(AnalogFinfetFoundation):
    """The template for finfet vertical extension block.  Used to add more routing tracks.

    Parameters
    ----------
    grid : :class:`bag.layout.routing.RoutingGrid`
            the :class:`~bag.layout.routing.RoutingGrid` instance.
    lib_name : str
        the layout library name.
    params : dict
        the parameter values.
    used_names : set[str]
        a set of already used cell names.
    """
    __metaclass__ = abc.ABCMeta

    def __init__(self, grid, lib_name, params, used_names):
        AnalogFinfetFoundation.__init__(self, grid, lib_name, params, used_names)

    @abc.abstractmethod
    def draw_od_edge(self, layout, temp_db, yc, w, tech_constants):
        """Draw od edge dummies.

        You can assume that self.array_box is already set.
        """
        pass

    def get_default_params(self):
        """Returns the default parameter dictionary.

        Override this method to return a dictionary of default parameter values.
        This returned dictionary should not include port_specs

        Returns
        -------
        default_params : dict[str, any]
            the default parameters dictionary.
        """
        return dict(mos_type='nch',
                    threshold='ulvt',
                    lch=16e-9,
                    w=8,
                    ext=0,
                    tech_constants=None,
                    )

    def get_layout_basename(self):
        """Returns the base name for this template.

        Returns
        -------
        base_name : str
            the base name of this template.
        """
        mos_type = self.params['mos_type']
        threshold = self.params['threshold']
        lch = self.params['lch']
        w = self.params['w']
        ext = self.params['ext']
        tech_str = self.params['tech_constants']['name']
        lch_str = float_to_si_string(lch)
        return '%s_%s_%s_l%s_w%d_ext%d_edge' % (tech_str, mos_type, threshold, lch_str, w, ext)

    def compute_unique_key(self):
        return self.get_layout_basename()

    def draw_layout(self, layout, temp_db,
                    mos_type='nch', threshold='lvt', lch=16e-9,
                    w=4, ext=0, tech_constants=None):
        """Draw the layout of this template.

        Override this method to create the layout.

        Parameters
        ----------
        layout : :class:`bag.layout.core.BagLayout`
            the BagLayout instance to draw the layout with.
        temp_db : :class:`bag.layout.template.TemplateDB`
            the TemplateDB instance.  Used to create new templates.
        mos_type : str
            the transistor type.  Either 'nch' or 'pch'
        threshold : str
            the transistor threshold flavor.
        lch : float
            the transistor channel length.
        w : float for int
            transistor width.
        ext : int
            number of fins to extend on the bottom.
        tech_constants : dict[str, any]
            the technology constants dictionary.  Must have the following entries:

            mos_fin_pitch : float
                the pitch between fins.
            mos_cpo_h : float
                the height of CPO layer.
            sd_pitch : float
                source and drain pitch of the transistor.
            implant_layers : list[str]
                list of implant/threshold layers to draw.
            name : str
                a string describing the process technology.  Used for identification purposes.
            mos_edge_num_dpo : int
                number of dummy polys at each edge.
            mos_edge_xext : float
                horizontal extension of CPO/implant layers over the array box left and right edges.
            mos_fin_h : float
                the height of the fin.
            nfin : int
                array box height in number of fin pitches.
            mos_core_cpo_po_ov : float
                overlap between CPO and PO.
            mos_edge_od_dy : float
                delta Y value from center of OD to array box bottom with 0 extension.
        """

        res = self.grid.get_resolution()

        mos_fin_h = tech_constants['mos_fin_h']
        mos_fin_pitch = tech_constants['mos_fin_pitch']
        ndum = tech_constants['mos_edge_num_dpo']
        xext = tech_constants['mos_edge_xext']
        sd_pitch = tech_constants['sd_pitch']
        nfin = tech_constants['nfin']
        mos_core_cpo_po_ov = tech_constants['mos_core_cpo_po_ov']
        mos_cpo_h = tech_constants['mos_cpo_h']

        if mos_type == 'ptap' or mos_type == 'ntap':
            extb = max(mos_core_cpo_po_ov - mos_cpo_h / 2.0, 0.0)
        else:
            extb = 0.0

        # draw foundation, include 1 PODE poly
        self.draw_foundation(layout, lch=lch, nfin=nfin + ext, fg=1,
                             nduml=ndum, ndumr=0, arr_box_ext=[xext, extb, 0.0, 0.0],
                             tech_constants=tech_constants)

        # draw OD/PODE
        od_yc = self.array_box.bottom + tech_constants['mos_edge_od_dy'] + ext * mos_fin_pitch
        lch_layout = lch / self.grid.get_layout_unit()
        od_h = mos_fin_h + (w - 1) * mos_fin_pitch
        xmid = (ndum + 0.5) * sd_pitch + xext
        xl = xmid - lch_layout / 2.0
        xr = xmid + lch_layout / 2.0
        box = BBox(xl, od_yc - od_h / 2.0, xr, od_yc + od_h / 2.0, res)
        layout.add_rect('OD', box)
        layout.add_rect('PODE', box, purpose='dummy1')

        # draw OD edge objects
        self.draw_od_edge(layout, temp_db, od_yc, w, tech_constants)


class AnalogFinfetBase(AnalogMosBase):
    """An abstract subclass of AnalogMosBase for finfet technology.

    Parameters
    ----------
    grid : :class:`bag.layout.routing.RoutingGrid`
            the :class:`~bag.layout.routing.RoutingGrid` instance.
    lib_name : str
        the layout library name.
    params : dict
        the parameter values.
    used_names : set[str]
        a set of already used cell names.
    tech_name : str
        the technology name.
    core_cls : class
        the Template class used to generate core transistor.
    edge_cls : class
        the Template class used to generate transistor edge block.
    ext_cls : class
        the Template class used to generate extension block.
    tech_constants : dict[str, any]
        the technology constants dictionary.
    """
    __metaclass__ = abc.ABCMeta

    def __init__(self, grid, lib_name, params, used_names,
                 tech_name, core_cls, edge_cls, ext_cls, tech_constants):
        AnalogMosBase.__init__(self, grid, lib_name, params, used_names, tech_name)
        self.core_cls = core_cls
        self.edge_cls = edge_cls
        self.ext_cls = ext_cls
        self.tech_constants = tech_constants

    @abc.abstractmethod
    def get_ext_params(self, ext_nfin):
        """Returns a dictionary of extension block parameters.

        Parameters
        ----------
        ext_nfin : int
            extension height in number of fins.

        Returns
        -------
        params : dict[str, any]
            the extension block parameters.
        """
        return {}

    @abc.abstractmethod
    def get_edge_params(self, core_ext):
        """Returns a dictionary of edge block parameters.

        Parameters
        ----------
        core_ext : int
            core height extension in number of fins.

        Returns
        -------
        params : dict[str, any] or
            the edge block parameters.
        """
        return {}

    @abc.abstractmethod
    def get_core_params(self, core_ext):
        """Returns a dictionary of core block parameters.

        Parameters
        ----------
        core_ext : int
            core height extension in number of fins.

        Returns
        -------
        params : dict[str, any] or
            the core block parameters.
        """
        return {}

    @abc.abstractmethod
    def get_core_info(self):
        """Returns core transistor properties with 0 extension useful for layout.

        Returns
        -------
        core_info : dict[str, any]
            core transistor properties dictionary.
        """
        return {}

    def draw_layout(self, layout, temp_db,
                    mos_type='nch', threshold='lvt', lch=16e-9, w=4, fg=4,
                    track_width=78e-9, track_space=210e-9,
                    g_tracks=1, ds_tracks=1):
        """Draw the layout of this template.

        Override this method to create the layout.

        Parameters
        ----------
        layout : :class:`bag.layout.core.BagLayout`
            the BagLayout instance to draw the layout with.
        temp_db : :class:`bag.layout.template.TemplateDB`
            the TemplateDB instance.  Used to create new templates.
        mos_type : str
            the transistor type.
        threshold : str
            the transistor threshold flavor.
        lch : float
            the transistor channel length.
        w : float for int
            the transistor width, or number of fins.
        fg : int
            the number of fingers.
        track_width : float
            the routing track width.
        track_space : float
            the routing track spacing.
        g_tracks : int
            minimum number of gate tracks.
        ds_tracks : int
            minimum number of drain/source tracks.
        """
        if fg <= 0:
            raise ValueError('Number of fingers must be positive.')

        # get technology constants
        mos_fin_pitch = self.tech_constants['mos_fin_pitch']
        mos_ext_nfin_min = self.tech_constants['mos_ext_nfin_min']

        # express track pitch as number of fin pitches
        layout_unit = self.grid.get_layout_unit()
        track_width /= layout_unit
        track_space /= layout_unit
        track_pitch = track_width + track_space
        track_nfin = int(round(track_pitch * 1.0 / mos_fin_pitch))
        if abs(track_pitch - track_nfin * mos_fin_pitch) >= self.grid.get_resolution():
            # check track_pitch is multiple of nfin.
            msg = 'track pitch = %.4g not multiples of fin pitch = %.4g' % (track_pitch, mos_fin_pitch)
            raise ValueError(msg)
        if track_nfin < mos_ext_nfin_min:
            # check a single track pitch is greater than or equal to minimum extension height.
            msg = 'track pitch = %.4g less than minimum extension height = %.4g' % (track_pitch,
                                                                                    mos_ext_nfin_min * mos_fin_pitch)
            raise ValueError(msg)

        # get extension needed to fit integer number of tracks
        core_info = self.get_core_info()
        core_nfin = core_info['nfin']
        core_tr_nfin = core_info['tr_nfin']

        # compute minimum number of tracks and needed bottom extension
        ntrack_min = int(np.ceil(core_nfin * 1.0 / track_nfin))
        bot_ext_nfin = track_nfin * ntrack_min - core_nfin

        # See if the first track is far enough from core transistor
        track_top_nfin = int(np.ceil((track_space / 2.0 + track_width) / mos_fin_pitch))
        track_top_nfin_max = core_tr_nfin + bot_ext_nfin
        if track_top_nfin > track_top_nfin_max:
            # first track from bottom too close to core transistor
            # add an additional track to increase spacing.
            bot_ext_nfin += track_nfin
            ntrack_min += 1

        # now calculate bottom/top extensions to account for gate tracks and drain/source tracks
        bot_ext_nfin += max(g_tracks - 1, 0) * track_nfin
        top_ext_nfin = max(ds_tracks - (ntrack_min - 1), 0) * track_nfin

        # determine if we need top/bottom extension blocks, or we should simply extend the core.
        if bot_ext_nfin < mos_ext_nfin_min:
            core_bot_ext = bot_ext_nfin
            bot_ext_nfin = 0
        else:
            core_bot_ext = 0

        # create left edge
        edge_params = self.get_edge_params(core_bot_ext)
        edge_blk = temp_db.new_template(params=edge_params, temp_cls=self.edge_cls)  # type: MicroTemplate
        edge_arr_box = edge_blk.array_box

        # draw bottom extension if needed, then compute lower-left array box coordinate.
        if bot_ext_nfin > 0:
            # draw bottom extension
            bot_ext_params = self.get_ext_params(bot_ext_nfin)
            blk = temp_db.new_template(params=bot_ext_params, temp_cls=self.ext_cls)  # type: MicroTemplate
            self.add_template(layout, blk, 'XBEXT')
            bot_ext_arr_box = blk.array_box

            dy = bot_ext_arr_box.top - edge_arr_box.bottom
            arr_box_left, arr_box_bottom = bot_ext_arr_box.left, bot_ext_arr_box.bottom
        else:
            dy = 0.0
            arr_box_left, arr_box_bottom = edge_arr_box.left, edge_arr_box.bottom

        # create core transistor.
        core_params = self.get_core_params(core_bot_ext)
        core_blk = temp_db.new_template(params=core_params, temp_cls=self.core_cls)  # type: MicroTemplate
        core_arr_box = core_blk.array_box

        # draw left edge
        self.add_template(layout, edge_blk, 'XLEDGE', loc=(0.0, dy))
        # draw core
        dx = edge_arr_box.right - core_arr_box.left
        self.add_template(layout, core_blk, 'XMOS', loc=(dx, dy))

        # draw right edge and compute top right array box coordinate.
        dx = dx + core_arr_box.right + edge_arr_box.width - edge_arr_box.left
        self.add_template(layout, edge_blk, 'XREDGE', loc=(dx, dy), orient='MY')
        arr_box_right = edge_arr_box.left + dx
        arr_box_top = edge_arr_box.top + dy

        # draw top extension and update top array box coordinate if needed
        if top_ext_nfin > 0:
            # draw top extension
            top_ext_params = self.get_ext_params(top_ext_nfin)
            blk = temp_db.new_template(params=top_ext_params, temp_cls=self.ext_cls)  # type: MicroTemplate
            top_ext_arr_box = blk.array_box
            self.add_template(layout, blk, 'XTEXT', loc=(0.0, arr_box_top - top_ext_arr_box.bottom))
            arr_box_top += top_ext_arr_box.height

        # set array box of this template
        self.array_box = BBox(arr_box_left, arr_box_bottom, arr_box_right, arr_box_top,
                              self.grid.get_resolution())


class AnalogMosConn(MicroTemplate):
    """An abstract template for analog mosfet connections.

    Connections drain, gate, and source to a metal layer that makes
    higher level connections relatively process independent.

    Parameters
    ----------
    grid : :class:`bag.layout.routing.RoutingGrid`
            the :class:`~bag.layout.routing.RoutingGrid` instance.
    lib_name : str
        the layout library name.
    params : dict
        the parameter values.
    used_names : set[str]
        a set of already used cell names.
    tech_name : str
        the technology name.
    """
    __metaclass__ = abc.ABCMeta

    def __init__(self, grid, lib_name, params, used_names, tech_name):
        self.tech_name = tech_name
        MicroTemplate.__init__(self, grid, lib_name, params, used_names)

    def get_layout_basename(self):
        """Returns the base name for this template.

        Returns
        -------
        base_name : str
            the base name of this template.
        """

        lch_str = float_to_si_string(self.params['lch'])
        w_str = float_to_si_string(self.params['w'])
        return '%s_l%s_w%s_fg%d_s%s_conn' % (self.tech_name,
                                             lch_str, w_str,
                                             self.params['fg'],
                                             self.params['sdir'])

    def compute_unique_key(self):
        return self.get_layout_basename()
