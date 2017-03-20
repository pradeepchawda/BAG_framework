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

"""This module contains commonly used technology related classes and functions.
"""
from __future__ import (absolute_import, division,
                        print_function, unicode_literals)
# noinspection PyUnresolvedReferences,PyCompatibility
from builtins import *
from future.utils import with_metaclass

import os
import abc
import itertools
import pprint
from typing import List, Union, Tuple

import numpy as np
import h5py
import openmdao.api as omdao

from .. import data
from ..math.interpolate import interpolate_grid
from bag.math.dfun import VectorDiffFunction, DiffFunction
from ..mdao.core import GroupBuilder
from ..io import fix_string, to_bytes


def _equal(a, b, rtol, atol):
    """Returns True if a == b.  a and b are both strings, floats or numpy arrays."""
    # python 2/3 compatibility: convert raw bytes to string
    a = fix_string(a)
    b = fix_string(b)

    if isinstance(a, str):
        return a == b
    return np.allclose(a, b, rtol=rtol, atol=atol)


def _equal_list(a, b, rtol, atol):
    """Returns True if a == b.  a and b are list of strings/floats/numpy arrays."""
    if len(a) != len(b):
        return False
    for a_item, b_item in zip(a, b):
        if not _equal(a_item, b_item, rtol, atol):
            return False
    return True


def _index_in_list(item_list, item, rtol, atol):
    """Returns index of item in item_list, with tolerance checking for floats."""
    for idx, test in enumerate(item_list):
        if _equal(test, item, rtol, atol):
            return idx
    return -1


def _in_list(item_list, item, rtol, atol):
    """Returns True if item is in item_list, with tolerance checking for floats."""
    return _index_in_list(item_list, item, rtol, atol) >= 0


class CircuitCharacterization(with_metaclass(abc.ABCMeta, object)):
    """A class that handles characterization a circuit with simulation and saving simulation results to file.

    This class never overwrites old simulation data.  If you wish to overwrite it, rename or delete the file
    manually.

    Parameters
    ----------
    prj : bag.BagProject
        the BagProject instance.
    root_dir : str
        path to the root simulation data directory.  Supports environment variables
    output_list : list[str]
        list of output names to save.
    impl_lib : str
        the library to store the generated testbenches/schematics/layout.
    impl_cell : str
        the generated schematic cell name.
    layout_params : dict[str, any]
        dictionary of layout specific parameters.
    compression : str
        HDF5 compression method.
    rtol : float
        relative tolerance used to compare constants/sweep parameters/sweep attributes.
    atol : float
        relative tolerance used to compare constants/sweep parameters/sweep attributes.
    """

    def __init__(self, prj, root_dir, output_list, impl_lib, impl_cell, layout_params,
                 compression='gzip', rtol=1e-5, atol=1e-18):
        self._prj = prj
        self._root_dir = os.path.abspath(os.path.expandvars(root_dir))
        self._output_list = output_list
        self._impl_lib = impl_lib
        self._impl_cell = impl_cell
        self._layout_params = layout_params
        self._compression = compression
        self._rtol = rtol
        self._atol = atol

    @property
    def prj(self):
        """the BagProject instance."""
        return self._prj

    @property
    def output_list(self):
        """Returns the list of output names."""
        return self._output_list

    @abc.abstractmethod
    def create_schematic_design(self, constants, attrs, **kwargs):
        """Create a new DesignModule with the given parameters.

        Parameters
        ----------
        constants : dict[str, any]
            simulation constants dictionary.
        attrs : dict[str, any]
            attributes dictionary.
        kwargs : dict[str, any]
            additional schematic parameters.

        Returns
        -------
        dsn : bag.design.Module
            the DesignModule with the given transistor parameters.
        """
        return None

    @abc.abstractmethod
    def create_layout(self, temp_db, lib_name, cell_name, layout_params, **kwargs):
        """Create layout with the given parameters.

        Parameters
        ----------
        temp_db : bag.layout.template.TemplateDB
            the TemplateDB instance used to create templates.
        lib_name : str
            library to save the layout.
        cell_name : str
            layout cell name.
        layout_params : dict[str, any]
            the layout parameters dictionary.
        kwargs : dict[str, any]
            additional parameters needed to create layout.
        """
        pass

    @abc.abstractmethod
    def setup_testbench(self, dut_lib, dut_cell, impl_lib, env_list, constants, sweep_params, extracted):
        """Create and setup the characterization testbench.

        Parameters
        ----------
        dut_lib : str
            the device-under-test library name.
        dut_cell : str
            the device-under-test cell name.
        impl_lib : str
            library to put the created testbench in.
        env_list : list[str]
            a list of simulation environments to characterize.
        constants : dict[str, any]
            simulation constants.
        sweep_params : dict[str, any]
            the sweep parameters dictionary, the values are (<start>, <stop>, <num_points>).
        extracted : bool
            True to run extracted simulation.

        Returns
        -------
        tb : bag.core.Testbench
            the resulting testbench object.
        """
        return None

    @abc.abstractmethod
    def get_sim_file_name(self, constants):
        """Returns the simulation file name with the given constants.

        Parameters
        ----------
        constants : dict[str, any]
            the constants dictionary.

        Returns
        -------
        fname : str
            the simulation file name.
        """
        return ''

    def _get_env_result(self, sim_results, env):
        """Extract results from a given simulation environment from the given data.

        all output sweep parameter order and data shape must be the same.

        Parameters
        ----------
        sim_results : dict[string, any]
            the simulation results dictionary
        env : str
            the target simulation environment

        Returns
        -------
        results : dict[str, any]
            the results from a given simulation environment.
        sweep_list : list[str]
            a list of sweep parameter order.
        """
        if 'corner' not in sim_results:
            # no corner sweep anyways
            results = {output: sim_results[output] for output in self.output_list}
            sweep_list = sim_results['sweep_params'][self.output_list[0]]
            return results, sweep_list

        corner_list = sim_results['corner'].tolist()
        results = {}
        # we know all sweep order and shape is the same.
        test_name = self.output_list[0]
        sweep_list = list(sim_results['sweep_params'][test_name])
        shape = sim_results[test_name].shape
        # make numpy array slice index list
        index_list = [slice(0, l) for l in shape]
        if 'corner' in sweep_list:
            idx = sweep_list.index('corner')
            index_list[idx] = corner_list.index(env)
            del sweep_list[idx]

        # store outputs in results
        for output in self.output_list:
            results[output] = sim_results[output][index_list]

        return results, sweep_list

    def _get_missing_sweep_config(self, fname, constants, sweep_attrs, env_list, sweep_params):
        """Return missing attributes/env combination in the existing file.

        If the file does not exist, create an empty file.

        Parameters
        ----------
        fname : str
            file containing existing data.
        constants : dict[str, any]
            constants dictionary.
        sweep_attrs : dict[str, list]
            dictionary from sweep attributes to list of sweep values.
        env_list : list[str]
            a list of simulation environments to characterize.
        sweep_params : dict[str, any]
            the sweep parameters dictionary, the values are (<start>, <stop>, <num_points>).

        Returns
        -------
        attr_list : list[str]
            list of attribute names
        total_combo : dict
            a dictionary from attribute combinations to env_list, which are the missing combinations in the file.
        """
        attr_list = list(sweep_attrs.keys())
        combo_iter = itertools.product(*(sweep_attrs[attr_name] for attr_name in attr_list))
        total_combo = [(combo, list(env_list)) for combo in combo_iter]

        if not os.path.exists(fname):
            # create empty file
            dir_name = os.path.dirname(fname)
            if not os.path.exists(dir_name):
                os.makedirs(dir_name)

            with h5py.File(fname, 'w') as f:
                for key, val in constants.items():
                    f.attrs[key] = val
                for key, val in sweep_params.items():
                    f.attrs[key] = val

            return attr_list, total_combo

        # check file is consistent.
        with h5py.File(fname, 'r') as f:
            # check constants are consistent.
            for key, val in constants.items():
                if not _equal(val, f.attrs[key], self._rtol, self._atol):
                    raise Exception('file %s constant %s = %s != %s' % (fname, key, f.attrs[key], val))

            # check sweep parameters are consistent.
            for key, val in sweep_params.items():
                if not _equal(val, f.attrs[key], self._rtol, self._atol):
                    raise Exception('file %s sweep %s = %s != %s' % (fname, key, f.attrs[key], val))

            # delete existing attribute/env configurations.
            for gname in f:
                grp = f[gname]
                key = tuple((grp.attrs[attr_name] for attr_name in attr_list))
                for combo, env_list in total_combo:
                    if _equal_list(combo, key, self._rtol, self._atol):
                        # remove existing environment.
                        try:
                            env_list.remove(grp.attrs['env'])
                        except ValueError:
                            pass
                        break

        return attr_list, total_combo

    def _record_data(self, fname, results, attributes, env_list):
        """Save the given simulation data to file.

        Parameters
        ----------
        fname : str
            simulation file name.
        results : dict[str, any]
            the simulation result dictionary.
        attributes : dict[str, any]
            the dataset attributes dictionary.
        env_list : list[str]
            a list of simulation environments to record.
        """
        if 'env' in attributes or 'sweep_params' in attributes:
            raise ValueError('Cannot have attributes named "env" or "sweep_params".')

        with h5py.File(fname, 'a') as f:
            for env in env_list:
                env_result, sweep_list = self._get_env_result(results, env)

                grp = f.create_group('%d' % len(f))
                for key, val in attributes.items():
                    grp.attrs[key] = val
                # h5py workaround: explicitly store strings as encoded unicode data
                grp.attrs['env'] = to_bytes(env)
                grp.attrs['sweep_params'] = [to_bytes(swp) for swp in sweep_list]

                for name, val in env_result.items():
                    grp.create_dataset(name, data=val, compression=self._compression)

    def simulate(self, temp_db, constants, sweep_attrs, sweep_params, env_list,
                 sch_kwargs=None, lay_kwargs=None, extracted=True, rcx_params=None, skip_lvs=False):
        """Run simulations and save results to raw simulation data file.

        Parameters
        ----------
        temp_db : bag.layout.template.TemplateDB
            the TemplateDB instance used to create templates.
        constants : dict[str, any]
            constants dictionary.
        sweep_attrs : dict[str, list]
            dictionary from sweep attributes to list of sweep values.
        sweep_params : dict[str, any]
            the sweep parameters dictionary, the values are (<start>, <stop>, <num_points>).
        env_list : list[str]
            a list of simulation environments to characterize.
        sch_kwargs : dict[str, any]
            additional schematic creation parameters.
        lay_kwargs : dict[str, any]
            additional layout creation parameters.
        extracted : bool
            True to run extracted simulation.
        rcx_params : dict[str, any]
            Override RCX parameters.
        skip_lvs : bool
            True to directly run RCX and skip running LVS.  Set this to true if RCX runs LVS
            first anyways.
        """
        sch_kwargs = sch_kwargs or {}
        lay_kwargs = lay_kwargs or {}
        rcx_params = rcx_params or {}

        fname = os.path.join(self._root_dir, self.get_sim_file_name(constants))

        attr_list, total_combo = self._get_missing_sweep_config(fname, constants, sweep_attrs, env_list, sweep_params)

        for attr_values, env_list in total_combo:
            attr_table = dict(zip(attr_list, attr_values))

            if env_list:
                print('characterizing:\n %s\n' % pprint.pformat(attr_table))
                print('creating schematic')
                dsn = self.create_schematic_design(constants, attr_table, **sch_kwargs)
                dsn.implement_design(self._impl_lib, top_cell_name=self._impl_cell, erase=True)
                print('schematic done')

                if extracted:
                    print('creating layout')
                    layout_params = dsn.get_layout_params(**self._layout_params)
                    self.create_layout(temp_db, self._impl_lib, self._impl_cell, layout_params, **lay_kwargs)
                    print('layout done')

                    if not skip_lvs:
                        print('running lvs')
                        lvs_passed, lvs_log = self.prj.run_lvs(self._impl_lib, self._impl_cell)
                        if not lvs_passed:
                            raise Exception('oops lvs died.  See LVS log file %s' % lvs_log)
                        print('lvs passed')

                    print('running rcx')
                    rcx_passed, rcx_log = self.prj.run_rcx(self._impl_lib, self._impl_cell,
                                                           rcx_params=rcx_params)
                    if not rcx_passed:
                        raise Exception('oops rcx died.  See RCX log file %s' % rcx_log)
                    print('rcx passed')

                print('setup testbench')
                tb = self.setup_testbench(self._impl_lib, self._impl_cell, self._impl_lib,
                                          env_list, constants, sweep_params, extracted)
                print('testbench done')

                print('run simulation')
                tb.run_simulation()
                print('simulation done')

                results = data.load_sim_results(tb.save_dir)
                self._record_data(fname, results, attr_table, env_list)


class CharDB(with_metaclass(abc.ABCMeta, object)):
    """The abstract base class of a database of characterization data.

    This class provides useful query/optimization methods and ways to store/retrieve
    data.

    Parameters
    ----------
    root_dir : str
        path to the root characterization data directory.  Supports environment variables.
    constants : dict[str, any]
        constants dictionary.
    discrete_params : list[string]
        a list of parameters that should take on discrete values.
    init_params : dict[str, any]
        a dictionary of initial parameter values.  All parameters should be specified,
        and None should be used if the parameter value is not set.
    env_list : list[str]
        list of simulation environments to consider.
    update : bool
        By default, CharDB saves and load post-processed data directly.  If update is True,
        CharDB will update the post-process data from raw simulation data. Defaults to
        False.
    rtol : float
        relative tolerance used to compare constants/sweep parameters/sweep attributes.
    atol : float
        relative tolerance used to compare constants/sweep parameters/sweep attributes.
    compression : str
        HDF5 compression method.  Used only during post-processing.
    method : str
        interpolation method.
    opt_package : string
        default Python optimization package.  Supports 'scipy' or 'pyoptsparse'.  Defaults
        to 'scipy'.
    opt_method : string
        default optimization method.  Valid values depends on the optimization package.
        Defaults to 'SLSQP'.
    opt_settings : dict[str, any]
        optimizer specific settings.
    """

    def __init__(self, root_dir, constants, discrete_params, init_params, env_list,
                 update=None, rtol=1e-5, atol=1e-18, compression='gzip',
                 method='spline', opt_package='scipy', opt_method='SLSQP',
                 opt_settings=None, **kwargs):

        root_dir = os.path.abspath(os.path.expandvars(root_dir))

        if not os.path.isdir(root_dir):
            # error checking
            raise ValueError('Directory %s not found.' % root_dir)
        if 'env' in discrete_params:
            discrete_params.remove('env')

        if opt_method == 'IPOPT' and not opt_settings:
            # set default IPOPT settings
            opt_settings = dict(option_file_name='')

        self._discrete_params = discrete_params
        self._params = init_params.copy()
        self._env_list = env_list
        self._config = dict(opt_package=opt_package,
                            opt_method=opt_method,
                            opt_settings=opt_settings or {},
                            rtol=rtol,
                            atol=atol,
                            method=method,
                            )

        cache_fname = self.get_cache_file(root_dir, constants)
        if not os.path.isfile(cache_fname) or update:
            sim_fname = self.get_sim_file(root_dir, constants)
            results = self._load_sim_data(sim_fname, constants, discrete_params)
            sim_data, total_params, total_values, self._constants = results
            self._data = self.post_process_data(sim_data, total_params, total_values, self._constants)

            # save to cache
            with h5py.File(cache_fname, 'w') as f:
                for key, val in self._constants.items():
                    f.attrs[key] = val
                sp_grp = f.create_group('sweep_params')
                # h5py workaround: explicitly store strings as encoded unicode data
                sp_grp.attrs['sweep_order'] = [to_bytes(swp) for swp in total_params]
                for par, val_list in zip(total_params, total_values):
                    if val_list.dtype.kind == 'U':
                        # unicode array, convert to raw bytes array
                        val_list = val_list.astype('S')
                    sp_grp.create_dataset(par, data=val_list, compression=compression)
                data_grp = f.create_group('data')
                for name, data_arr in self._data.items():
                    data_grp.create_dataset(name, data=data_arr, compression=compression)
        else:
            # load from cache
            with h5py.File(cache_fname, 'r') as f:
                self._constants = dict(iter(f.attrs.items()))
                sp_grp = f['sweep_params']
                total_params = [fix_string(swp) for swp in sp_grp.attrs['sweep_order']]
                total_values = [self._convert_hdf5_array(sp_grp[par][()]) for par in total_params]
                data_grp = f['data']
                self._data = {name: data_grp[name][()] for name in data_grp}

        # change axes location so discrete parameters are at the start of sweep_params
        env_disc_params = ['env'] + discrete_params
        for idx, dpar in enumerate(env_disc_params):
            if total_params[idx] != dpar:
                # swap
                didx = total_params.index(dpar)
                ptmp = total_params[idx]
                vtmp = total_values[idx]
                total_params[idx] = total_params[didx]
                total_values[idx] = total_values[didx]
                total_params[didx] = ptmp
                total_values[didx] = vtmp
                for key, val in self._data.items():
                    self._data[key] = np.swapaxes(val, idx, didx)

        sidx = len(self._discrete_params) + 1
        self._cont_params = total_params[sidx:]
        self._cont_values = total_values[sidx:]
        self._discrete_values = total_values[1:sidx]
        self._env_values = total_values[0]

        # get lazy function table.
        shape = [total_values[idx].size for idx in range(len(env_disc_params))]

        fun_name_iter = itertools.chain(iter(self._data.keys()), self.derived_parameters())
        # noinspection PyTypeChecker
        self._fun = {name: np.full(shape, None, dtype=object) for name in fun_name_iter}

    @staticmethod
    def _convert_hdf5_array(arr):
        """Check if raw bytes array, if so convert to unicode array."""
        if arr.dtype.kind == 'S':
            return arr.astype('U')
        return arr

    def _load_sim_data(self, fname, constants, discrete_params):
        """Returns the simulation data.

        Parameters
        ----------
        fname : str
            the simulation filename.
        constants : dict[str, any]
            the constants dictionary.
        discrete_params : list[str]
            a list of parameters that should take on discrete values.

        Returns
        -------
        data_dict : dict[str, numpy.array]
            a dictionary from output name to data as numpy array.
        master_attrs : list[str]
            list of attribute name for each dimension of numpy array.
        master_values : list[numpy.array]
            list of attribute values for each dimension.
        file_constants : dict[str, any]
            the constants dictionary in file.
        """
        if not os.path.exists(fname):
            raise ValueError('Simulation file %s not found.' % fname)

        rtol, atol = self.get_config('rtol'), self.get_config('atol')  # type: float

        master_attrs = None
        master_values = None
        master_dict = None
        file_constants = None
        with h5py.File(fname, 'r') as f:
            # check constants is consistent
            for key, val in constants.items():
                if not _equal(val, f.attrs[key], rtol, atol):
                    raise ValueError('sim file attr %s = %s != %s' % (key, f.attrs[key], val))

            # simple error checking.
            if len(f) == 0:
                raise ValueError('simulation file has no data.')

            # check that attributes sweep forms regular grid.
            attr_table = {}
            for gname in f:
                grp = f[gname]
                for key, val in grp.attrs.items():
                    # convert raw bytes to unicode
                    # python 2/3 compatibility: convert raw bytes to string
                    val = fix_string(val)

                    if key != 'sweep_params':
                        if key not in attr_table:
                            attr_table[key] = []
                        val_list = attr_table[key]
                        if not _in_list(val_list, val, rtol, atol):
                            val_list.append(val)

            expected_len = 1
            for val in attr_table.values():
                expected_len *= len(val)

            if expected_len != len(f):
                raise ValueError('Attributes of f does not form complete sweep. '
                                 'Expect length = %d, but actually = %d.' % (expected_len, len(f)))

            # check all discrete parameters in attribute table.
            for disc_par in discrete_params:
                if disc_par not in attr_table:
                    raise ValueError('Discrete attribute %s not found' % disc_par)

            # get attribute order
            attr_order = sorted(attr_table.keys())
            # check all non-discrete attribute value list lies on regular grid
            attr_values = [np.array(sorted(attr_table[attr])) for attr in attr_order]
            for attr, aval_list in zip(attr_order, attr_values):
                if attr not in discrete_params and attr != 'env':
                    test_vec = np.linspace(aval_list[0], aval_list[-1], len(aval_list), endpoint=True)
                    if not np.allclose(test_vec, aval_list, rtol=rtol, atol=atol):
                        raise ValueError('Attribute %s values do not lie on regular grid' % attr)

            # consolidate all data into one giant numpy array.
            # first compute numpy array shape
            test_grp = f['0']
            sweep_params = [fix_string(tmpvar) for tmpvar in test_grp.attrs['sweep_params']]

            # get constants dictionary
            file_constants = {}
            for key, val in f.attrs.items():
                if key not in sweep_params:
                    file_constants[key] = val

            master_attrs = attr_order + sweep_params
            swp_values = [np.linspace(f.attrs[var][0], f.attrs[var][1], f.attrs[var][2],
                                      endpoint=True) for var in sweep_params]  # type: List[np.array]
            master_values = attr_values + swp_values
            master_shape = [len(val_list) for val_list in master_values]
            master_index = [slice(0, n) for n in master_shape]
            master_dict = {}
            for gname in f:
                grp = f[gname]
                # get index of the current group in the giant array.
                # Note: using linear search to compute index now, but attr_val_list should be small.
                for aidx, (attr, aval_list) in enumerate(zip(attr_order, attr_values)):
                    master_index[aidx] = _index_in_list(aval_list, grp.attrs[attr], rtol, atol)

                for output in grp:
                    dset = grp[output]
                    if output not in master_dict:
                        master_dict[output] = np.empty(master_shape, dtype=dset.dtype)
                    master_dict[output][master_index] = dset

        return master_dict, master_attrs, master_values, file_constants

    def __getitem__(self, param):
        """Returns the given parameter value.

        Parameters
        ----------
        param : str
            parameter name.

        Returns
        -------
        val : any
            parameter value.
        """
        return self._params[param]

    def __setitem__(self, key, value):
        """Sets the given parameter value.

        Parameters
        ----------
        key : str
            parameter name.
        value : any
            parameter value.  None to unset.
        """
        rtol, atol = self.get_config('rtol'), self.get_config('atol')

        if key in self._discrete_params:
            if value is not None:
                idx = self._discrete_params.index(key)
                if not _in_list(self._discrete_values[idx], value, rtol, atol):
                    raise ValueError('Cannot set discrete variable %s value to %s' % (key, value))
        elif key in self._cont_params:
            if value is not None:
                idx = self._cont_params.index(key)
                val_list = self._cont_values[idx]
                if value < val_list[0] or value > val_list[-1]:
                    raise ValueError('Variable %s value %s out of bounds.' % (key, value))
        else:
            raise ValueError('Unknown variable %s.' % key)

        self._params[key] = value

    def get_config(self, name):
        """Returns the configuration value.

        Parameters
        ----------
        name : string
            configuration name.

        Returns
        -------
        val : any
            configuration value.
        """
        return self._config[name]

    def set_config(self, name, value):
        """Sets the configuration value.

        Parameters
        ----------
        name : string
            configuration name.
        value : any
            configuration value.
        """
        if name not in self._config:
            raise ValueError('Unknown configuration %s' % name)
        self._config[name] = value

    @property
    def env_list(self):
        """The list of simulation environments to consider."""
        return self._env_list

    @env_list.setter
    def env_list(self, new_env_list):
        """Sets the list of simulation environments to consider."""
        self._env_list = new_env_list

    @classmethod
    def get_sim_file(cls, root_dir, constants):
        """Returns the simulation data file name.

        Parameters
        ----------
        root_dir : str
            absolute path to the root characterization data directory.
        constants : dict[str, any]
            constants dictionary.

        Returns
        -------
        fname : str
            the simulation data file name.
        """
        raise NotImplementedError('Not implemented')

    @classmethod
    def get_cache_file(cls, root_dir, constants):
        """Returns the post-processed characterization data file name.

        Parameters
        ----------
        root_dir : str
            absolute path to the root characterization data directory.
        constants : dict[str, any]
            constants dictionary.

        Returns
        -------
        fname : str
            the post-processed characterization data file name.
        """
        raise NotImplementedError('Not implemented')

    @classmethod
    def post_process_data(cls, sim_data, sweep_params, sweep_values, constants):
        """Postprocess simulation data.

        Parameters
        ----------
        sim_data : dict[str, np.array]
            the simulation data as a dictionary from output name to numpy array.
        sweep_params : list[str]
            list of parameter name for each dimension of numpy array.
        sweep_values : list[numpy.array]
            list of parameter values for each dimension.
        constants : dict[str, any]
            the constants dictionary.

        Returns
        -------
        data : dict[str, np.array]
            a dictionary of post-processed data.
        """
        raise NotImplementedError('Not implemented')

    @classmethod
    def derived_parameters(cls):
        """Returns a list of derived parameters."""
        return []

    @classmethod
    def compute_derived_parameters(cls, fdict):
        """Compute derived parameter functions.

        Parameters
        ----------
        fdict : dict[str, bag.math.dfun.DiffFunction]
            a dictionary from core parameter name to the corresponding function.

        Returns
        -------
        deriv_dict : dict[str, bag.math.dfun.DiffFunction]
            a dictionary from derived parameter name to the corresponding function.
        """
        return {}

    def _get_function_index(self, **kwargs):
        """Returns the function index corresponding to given discrete parameter values.

        simulation environment index will be set to 0

        Parameters
        ----------
        kwargs : dict[str, any]
            dictionary of discrete parameter values.

        Returns
        -------
        fidx_list : list[int]
            the function index.
        """
        rtol, atol = self.get_config('rtol'), self.get_config('atol')

        fidx_list = [0]
        for par, val_list in zip(self._discrete_params, self._discrete_values):
            val = kwargs.get(par, self[par])
            if val is None:
                raise ValueError('Parameter %s value not specified' % par)

            val_idx = _index_in_list(val_list, val, rtol, atol)
            if val_idx < 0:
                raise ValueError('Discrete parameter %s have illegal value %s' % (par, val))
            fidx_list.append(val_idx)

        return fidx_list

    def _get_function_helper(self, name, fidx_list):
        # type: (str, Union[List[int], Tuple[int]]) -> DiffFunction
        """Helper method for get_function()

        Parameters
        ----------
        name : str
            name of the function.
        fidx_list : Union[List[int], Tuple[int]]
            function index.

        Returns
        -------
        fun : DiffFunction
            the interpolator function.
        """
        # get function table index
        fidx_list = tuple(fidx_list)
        ftable = self._fun[name]
        if ftable[fidx_list] is None:
            if name in self._data:
                # core parameter
                char_data = self._data[name]

                # get scale list and data index
                scale_list = []
                didx = list(fidx_list)
                for vec in self._cont_values:
                    scale_list.append((vec[0], vec[1] - vec[0]))
                    didx.append(slice(0, vec.size))

                # make interpolator.
                cur_data = char_data[didx]
                method = self.get_config('method')
                ftable[fidx_list] = interpolate_grid(scale_list, cur_data, method=method)
            else:
                # derived parameter
                core_fdict = {fn: self._get_function_helper(fn, fidx_list) for fn in self._data}
                deriv_fdict = self.compute_derived_parameters(core_fdict)
                for fn, deriv_fun in deriv_fdict.items():
                    self._fun[fn][fidx_list] = deriv_fun

        return ftable[fidx_list]

    def get_function(self, name, **kwargs):
        # type: (str, **kwargs) -> VectorDiffFunction
        """Returns a function for the given output.

        Parameters
        ----------
        name : str
            name of the function.
        kwargs :
            dictionary of discrete parameter values.

        Returns
        -------
        output : VectorDiffFunction
            the output vector function.
        """
        fidx_list = self._get_function_index(**kwargs)
        fun_list = []
        for env in self.env_list:
            env_idx = np.where(self._env_values == env)[0][0]
            fidx_list[0] = env_idx
            fun_list.append(self._get_function_helper(name, fidx_list))
        return VectorDiffFunction(fun_list)

    def get_scalar_function(self, name, env='', **kwargs):
        # type: (str, str, **kwargs) -> DiffFunction
        """Returns a scalar function for the given output for one simulation environment.

        Parameters
        ----------
        name : str
            name of the function.
        env : str
            the simulation environment name.
        kwargs :
            dictionary of discrete parameter values.

        Returns
        -------
        output : DiffFunction
            the output vector function.
        """
        if not env:
            if len(self._env_list) > 1:
                raise ValueError('More than one simulation environment is defined.')
            env = self._env_list[0]
        fidx_list = self._get_function_index(**kwargs)
        env_idx = np.where(self._env_values == env)[0][0]
        fidx_list[0] = env_idx
        return self._get_function_helper(name, fidx_list)

    def get_fun_sweep_params(self):
        """Returns interpolation function sweep parameter names and values.

        Returns
        -------
        sweep_params : list[str]
            list of parameter names.
        sweep_range : list[(float, float)]
            list of parameter range
        """
        return self._cont_params, [(vec[0], vec[-1]) for vec in self._cont_values]

    def _get_fun_arg(self, **kwargs):
        """Make numpy array of interpolation function arguments."""
        val_list = []
        for par in self._cont_params:
            val = kwargs.get(par, self[par])
            if val is None:
                raise ValueError('Parameter %s value not specified.' % par)
            val_list.append(val)

        return np.array(val_list)

    def query(self, **kwargs):
        """Query the database for the values associated with the given parameters.

        All parameters must be specified.

        Parameters
        ----------
        kwargs : dict[str, any]
            parameter values.

        Returns
        -------
        results : dict[str, float]
            the characterization results.
        """
        results = {}
        arg = self._get_fun_arg(**kwargs)
        for name in self._data:
            fun = self.get_function(name, **kwargs)
            results[name] = fun(arg)

        for var in itertools.chain(self._discrete_params, self._cont_params):
            results[var] = kwargs.get(var, self[var])

        results.update(self.compute_derived_parameters(results))

        return results

    def minimize(self, objective, define=None, cons=None, vector_params=None, debug=False, **kwargs):
        """Find operating point that minimizes the given objective.

        Parameters
        ----------
        objective : str
            the objective to minimize.  Must be a scalar.
        define : list[(str, int)]
            list of expressions to define new variables.  Each
            element of the list is a tuple of string and integer.  The string
            contains a python assignment that computes the variable from
            existing ones, and the integer indicates the variable shape.

            Note that define can also be used to enforce relationships between
            existing variables.  Using transistor as an example, defining
            'vgs = vds' will force the vgs of vds of the transistor to be
            equal.
        cons : dict[string, dict[string, float]]
            a dictionary from variable name to constraints of that variable.
            see OpenMDAO documentations for details on constraints.
        vector_params : set[str]
            set of input variables that are vector instead of scalar.  An input
            variable is a vector if it can change across simulation environments.
        debug : bool
            True to enable debugging messages.  Defaults to False.
        kwargs : dict[str, any]
            known parameter values.

        Returns
        -------
        results : dict[str, np.array or float]
            the results dictionary.
        """
        cons = cons or {}
        fidx_list = self._get_function_index(**kwargs)
        builder = GroupBuilder()

        params_ranges = dict(zip(self._cont_params,
                                 ((vec[0], vec[-1]) for vec in self._cont_values)))
        # add functions
        fun_name_iter = itertools.chain(iter(self._data.keys()), self.derived_parameters())
        for name in fun_name_iter:
            fun_list = []
            for idx, env in enumerate(self.env_list):
                fidx_list[0] = idx
                fun_list.append(self._get_function_helper(name, fidx_list))

            builder.add_fun(name, fun_list, self._cont_params, params_ranges,
                            vector_params=vector_params)

        # add expressions
        for expr, ndim in define:
            builder.add_expr(expr, ndim)

        # update input bounds from constraints
        input_set = builder.get_inputs()
        var_list = builder.get_variables()

        for name in input_set:
            if name in cons:
                setup = cons[name]
                if 'equals' in setup:
                    eq_val = setup['equals']
                    builder.set_input_limit(name, equals=eq_val)
                else:
                    vmin = vmax = None
                    if 'lower' in setup:
                        vmin = setup['lower']
                    if 'upper' in setup:
                        vmax = setup['upper']
                    builder.set_input_limit(name, lower=vmin, upper=vmax)

        # build the group and make the problem
        grp, input_bounds = builder.build()

        top = omdao.Problem()
        top.root = grp

        opt_package = self.get_config('opt_package')  # type: str
        opt_settings = self.get_config('opt_settings')

        if opt_package == 'scipy':
            driver = top.driver = omdao.ScipyOptimizer()
            print_opt_name = 'disp'
        elif opt_package == 'pyoptsparse':
            driver = top.driver = omdao.pyOptSparseDriver()
            print_opt_name = 'print_results'
        else:
            raise ValueError('Unknown optimization package: %s' % opt_package)

        driver.options['optimizer'] = self.get_config('opt_method')
        driver.options[print_opt_name] = debug
        driver.opt_settings.update(opt_settings)

        # add constraints
        constants = {}
        for name, setup in cons.items():
            if name not in input_bounds:
                # add constraint
                driver.add_constraint(name, **setup)

        # add inputs
        for name in input_set:
            eq_val, lower, upper, ndim = input_bounds[name]
            val = kwargs.get(name, self[name])  # type: float
            if val is None:
                val = eq_val
            comp_name = 'comp__%s' % name
            if val is not None:
                val = np.atleast_1d(np.ones(ndim) * val)
                constants[name] = val
                top.root.add(comp_name, omdao.IndepVarComp(name, val=val), promotes=[name])
            else:
                avg = (lower + upper) / 2.0
                span = upper - lower
                val = np.atleast_1d(np.ones(ndim) * avg)
                top.root.add(comp_name, omdao.IndepVarComp(name, val=val), promotes=[name])
                driver.add_desvar(name, lower=lower, upper=upper, adder=-avg, scaler=1.0 / span)
                # driver.add_desvar(name, lower=lower, upper=upper)

        # add objective and setup
        driver.add_objective(objective)
        top.setup(check=debug)

        # somehow html file is not viewable.
        if debug:
            omdao.view_model(top, outfile='CharDB_debug.html')

        # set constants
        for name, val in constants.items():
            top[name] = val

        top.run()

        results = {var: kwargs.get(var, self[var]) for var in self._discrete_params}
        for var in var_list:
            results[var] = top[var]

        return results
