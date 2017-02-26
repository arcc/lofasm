"""This is a script/module for checking and parsing file information to an astropy table.
Copyright (c) 2016 Jing Luo.
"""
import os
import astropy.table as table
from astropy import log
from astropy.io import ascii
import astropy.units as u
import numpy as np
from ..formats.format import DataFormat
from .info_collector import InfoCollector

class LofasmFileInfo(object):
    """This class provides a storage for a list of lofasm files information
    and set of methods to check the information.
    """
    def __init__(self, directory='.', add_col_names=[], check_subdir=False):
        """
        This is a class for reading a directory's the lofasm related file or
        directories and parsing the information to an astropy table. It provides
        the writing the information to a text file as well.

        Notes
        -----
        This class only applies to one directory.

        Parameter
        ----------
        dir : str, optional
            Filename for the directory.
        """
        # Get all the files for the directory.
        all_files = os.listdir(directory)
        self.directory = directory
        self.directory_abs_path = os.path.abspath(self.directory)
        self.directory_basename = os.path.basename(self.directory_abs_path.rstrip(os.sep))
        # different file category
        self.formats = {}
        # instantiate format classes
        for k, kv in zip(DataFormat._format_list.keys(), DataFormat._format_list.values()):
            self.formats[k] = kv()
        # set up the file category list depends on the formats
        self.files, self.num_data_files = self.check_file_format(all_files, self.directory)
        num_info_files = len(self.files['info'])
        if num_info_files < 1:
            self.info_file_name = '.info'
        else:
            if num_info_files > 1:
                log.warn("More then one .info file detected, " \
                         "use '%s' as information file." % self.files['info'][0])
            self.info_file_name = self.files['info'][0]
        if self.num_data_files > 0 or len(self.files['data_dir']) > 0 or \
            len(self.files['info']) > 0:
            self.is_data_dir = True
        else:
            self.is_data_dir = False
        self.built_in_collectors = {}
        self.new_files = []
        self.table_update = False
        # Those are the default column names
        self.col_names = ['station', 'channel', 'hdr_type', 'start_time'] + add_col_names
        self.setup_info_table()
        if check_subdir:
            self.process_data_dirs()

    def check_file_format(self, files, directory='.'):
        """
        This is a class method for checking file format. It only log the lofasm
        related files.
        """
        # Check file format
        file_format = {}
        file_format['dir'] = []
        file_format['info'] = []
        file_format['data_dir'] = []
        for fn in files:
            f = os.path.join(directory, fn)
            if f.endswith('.info'):
                file_format['info'].append(fn)
            if os.path.isdir(f):
                file_format['dir'].append(fn)
            else:
                for k, kc in zip(self.formats.keys(), self.formats.values()):
                    if k not in file_format.keys():
                        file_format[k] = []
                    if kc.is_format(f) and k != 'data_dir':
                        file_format[k].append(fn)
                        break
        # check dirs
        for d in file_format['dir']:
            if self.check_dir(d):
                file_format['data_dir'] += [d,]
        num_data_files = 0
        for k, v in file_format.items():
            if k not in ['info', 'dir','data_dir']:
                num_data_files += len(v)

        return file_format, num_data_files

    def check_dir(self, d):
        path_d = os.path.join(self.directory_abs_path, d)
        dirclass = LofasmFileInfo(path_d)
        if dirclass.num_data_files == 0 and dirclass.files['info'] == []:
            if dirclass.files['data_dir'] != []:
                return True
            else:
                # check contained dirs
                for subd in dirclass.files['dir']:
                    sudbpath = os.path.join(dirclass.directory_abs_path, subd)
                    subdirclass = LofasmFileInfo(subdpath)
                    if subdirclass.data_dir.is_data_dir:
                        return True
                    else:
                        continue
        else:
            return True


    def get_format_map(self):
        """ List all the file name as the key and the formats as the value.
        """
        data_files = []
        file_formats = []
        for tp, flist in zip(self.files.keys(), self.files.values()):
            if tp == 'dir':  # Do not process dir key.
                continue
            if not tp == 'info':
                tpl = [tp] * len(flist)
                data_files += flist
                file_formats += tpl
        format_map = dict(zip(data_files, file_formats))
        return format_map

    def get_col_collector(self, cols):
        """
        This is a method for get column information collector instances from built-in
        collectors.
        """
        curr_col_collector = {}
        for coln in cols:
            if coln in InfoCollector._info_name_list.keys():
                curr_col_collector[coln] = InfoCollector._info_name_list[coln]()
        return curr_col_collector

    def setup_info_table(self):
        format_map = self.get_format_map()
        # Check out info_file
        info_file = os.path.join(self.directory_abs_path, self.info_file_name)
        if os.path.isfile(info_file):
            self.info_table = table.Table.read(info_file, format='ascii.ecsv')
            curr_col = self.info_table.keys()
            # Process the new files.
            self.new_files = list(set(format_map.keys()) - set(self.info_table['filename']))
            if self.new_files != []:
                new_file_tp = [format_map[f] for f in self.new_files]
                new_f_table = table.Table([self.new_files, new_file_tp], \
                                           names=('filename', 'fileformat'))
                curr_col_collector = self.get_col_collector(curr_col)
                new_f_table = self.add_columns(curr_col_collector, new_f_table)
                self.info_table = table.vstack([self.info_table, new_f_table])
                if 'data_dir' in new_file_tp:
                    self.info_table.meta['haschild'] = True
                self.table_update = True
        else:
            if len(self.files['data_dir']) > 0:
                haschild = True
            else:
                haschild = False
            self.info_table = table.Table([format_map.keys(), format_map.values()], \
                                          names=('filename', 'fileformat'),\
                                          meta={'name':self.directory_basename + '_info_table',
                                                'haschild': haschild})
            col_collector = self.get_col_collector(self.col_names)
            self.info_table = self.add_columns(col_collector, self.info_table)
            self.table_update = True

    def add_columns(self, col_collectors, target_table, overwrite=False):
        """
        This method is a function add a column to info table.
        Parameter
        ---------
        col_collectors : dictionary
            The dictionary has to use the column name as the key, and the associated
            column information collector as the value.
        target_table : astropy table
            The table has to have column 'filename' and 'fileformat'.
        """
        col_info = {}
        # Check if col_name in the table.
        for cn in col_collectors.keys():
            if cn in target_table.keys() and not overwrite:
                log.warn("Column '%s' exists in the table. If you want to"
                         " overwrite the column please set  'overwrite'"
                         " flag True." % cn)
                continue
            else:
                col_info[cn] = []

        for fn, fmt in zip(target_table['filename'], target_table['fileformat']):
            f = os.path.join(self.directory, fn)
            f_obj = self.formats[fmt].instantiate_format_cls(f)
            for k in col_info.keys():
                try:
                    cvalue = col_collectors[k].collect_method[fmt](f_obj)
                except NotImplementedError:
                    cvalue = None
                col_info[k].append(cvalue)
            try:
                f_obj.close()
            except:
                pass
        for key in col_info.keys():
            target_table[key] = col_info[key]
            if key not in self.col_names:
                self.col_names.append(key)
        self.table_update = True
        return target_table

    def write_info_table(self):
        outpath = os.path.join(self.directory_abs_path, self.info_file_name)
        if self.table_update:
            self.info_table.write(outpath, format='ascii.ecsv', overwrite=True)

    def process_data_dirs(self):
        for d in self.files['data_dir']:
            path_d = os.path.join(self.directory_abs_path, d)
            dirclass = LofasmFileInfo(path_d, check_subdir=True)
            add_col = []
            for c in self.col_names:
                if c not in dirclass.col_names:
                    add_col.append(c)
            new_col_collector = self.get_col_collector(add_col)
            dirclass.info_table = dirclass.add_columns(new_col_collector, dirclass.info_table)
            dirclass.write_info_table()
