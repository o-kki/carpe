# -*- coding: utf-8 -*-
"""module for DEFA."""
import os
import hashlib
import configparser
import zipfile
from zipfile import ZipFile
from zipfile import BadZipFile
import xml.etree.ElementTree as ET
from datetime import datetime

from elasticsearch import Elasticsearch, helpers

from modules import manager
from modules import interface


class DEFAConnector(interface.ModuleConnector):
    NAME = 'defa_connector'
    DESCRIPTION = 'Module for DEFA'

    _plugin_classes = {}

    def __init__(self):
        super(DEFAConnector, self).__init__()

    def Connect(self, par_id, configuration, source_path_spec, knowledge_base):

        if configuration.standalone_check:
            this_file_path = os.path.dirname(os.path.abspath(__file__)) + os.sep + 'schema' + os.sep
            # 모든 yaml 파일 리스트
            yaml_list = [this_file_path + 'lv1_file_document.yaml']

            # 모든 테이블 리스트
            table_list = ['lv1_file_document']

            if not self.check_table_from_yaml(configuration, yaml_list, table_list):
                return False

        # 선택한 플러그인 파일만 읽어오기
        hwp_plugin = None
        doc_plugin = None
        docx_plugin = None
        ppt_plugin = None
        pptx_plugin = None
        xls_plugin = None
        xlsx_plugin = None
        pdf_plugin = None

        query_separator = self.GetQuerySeparator(source_path_spec, configuration)
        path_separator = self.GetPathSeparator(source_path_spec)
        # sig_type -> extension 임시 변경,
        query = f"SELECT name, parent_path, sig_type, extension, mtime, atime, ctime, etime, mtime_nano, atime_nano, " \
                f"ctime_nano, etime_nano, additional_mtime, additional_atime, additional_ctime, additional_etime, " \
                f"additional_mtime_nano, additional_atime_nano, additional_ctime_nano, additional_etime_nano, inode " \
                f"FROM file_info WHERE par_id='{par_id}'" \
                f"and parent_path not like '%{query_separator}Hnc{query_separator}Office%' " \
                f"and parent_path not like '%$Recycle.Bin{query_separator}S-1-5-21%' and name not like '$I%' and ("  # and parent_path not like '%_damaged/%' 임시

        for i in range(0, len(self._plugins)):
            if self._plugins[i].plugin_name == 'HWP':
                query += " LOWER(extension) = 'hwp' "
                hwp_plugin = self._plugins[i]
            elif self._plugins[i].plugin_name == 'DOC':
                query += " LOWER(extension) = 'doc' "
                doc_plugin = self._plugins[i]
            elif self._plugins[i].plugin_name == 'PPT':
                query += " LOWER(extension) = 'ppt' "
                ppt_plugin = self._plugins[i]
            elif self._plugins[i].plugin_name == 'XLS':
                query += " LOWER(extension) = 'xls' "
                xls_plugin = self._plugins[i]
            elif self._plugins[i].plugin_name == 'DOCX':
                query += " LOWER(extension) = 'docx' "
                docx_plugin = self._plugins[i]
            elif self._plugins[i].plugin_name == 'PPTX':
                query += " LOWER(extension) = 'pptx' "
                pptx_plugin = self._plugins[i]
            elif self._plugins[i].plugin_name == 'XLSX':
                query += " LOWER(extension) = 'xlsx' "
                xlsx_plugin = self._plugins[i]
            elif self._plugins[i].plugin_name == 'PDF':
                query += " LOWER(extension) = 'pdf' "
                pdf_plugin = self._plugins[i]

            if i == len(self._plugins) - 1:
                query += ");"
            else:
                query += "or "

        document_files = configuration.cursor.execute_query_mul(query)

        if document_files == -1 or len(document_files) == 0:
            print("There are no document files")
            return False

        ### Download Check ###
        query = f"SELECT name, parent_path FROM file_info WHERE par_id='{par_id}'" \
                f"and name like '%Zone.Identifier';"

        zone_identifier_files = configuration.cursor.execute_query_mul(query)
        tmp_list = list()
        for zone in zone_identifier_files:
            tmp_list.append(zone[1][4:] + path_separator + zone[0][:-16])
        zone_list = set(tmp_list)

        if configuration.standalone_check:
            insert_document = list()
        else:
            config = configparser.ConfigParser()
            conf_file = os.path.dirname(
                os.path.dirname(os.path.abspath(__file__))) + path_separator + 'config' + path_separator + 'carpe.conf'
            if not os.path.exists(conf_file):
                raise Exception('%s file does not exist.\n' % conf_file)
            config.read(conf_file)
            _host = config.get('elasticsearch', 'host')
            _port = config.getint('elasticsearch', 'port')
            _elastic_id = config.get('elasticsearch', 'id')
            _elastic_passwd = config.get('elasticsearch', 'passwd')
            _index_name = config.get('document', 'index')
            _type_name = config.get('document', 'type')
            es = Elasticsearch(hosts=_host, port=_port, http_auth=(_elastic_id, _elastic_passwd))

        tsk_file_system = self.get_tsk_file_system(source_path_spec, configuration)
        error_count = 0
        for document in document_files:
            document_path = document[1][document[1].find(path_separator):] + path_separator + document[
                0]  # document full path
            output_path = configuration.root_tmp_path + path_separator + configuration.case_id + path_separator + \
                          configuration.evidence_id + path_separator + par_id + path_separator \
                          + hashlib.sha1(document_path.encode('utf-8')).hexdigest()
            ole_path = output_path + path_separator + "ole"

            if not os.path.exists(output_path):
                os.makedirs(output_path)
                os.makedirs(ole_path)

            self.extract_file_to_path(tsk_file_system=tsk_file_system,
                                      inode=int(document[20]),
                                      file_name=document[0],
                                      output_path=output_path)

            # self.ExtractTargetFileToPath(
            #     source_path_spec=source_path_spec,
            #     configuration=configuration,
            #     file_path=document_path,
            #     output_path=output_path)

            file_path = output_path + path_separator + document[0]
            extension = document[3].lower()

            try:
                if extension == 'hwp':
                    result = hwp_plugin.Process(fp=file_path, ole_path=ole_path)
                elif extension == 'doc':
                    result = doc_plugin.Process(fp=file_path, ole_path=ole_path)
                elif extension == 'ppt':
                    result = ppt_plugin.Process(fp=file_path, ole_path=ole_path)
                elif extension == 'xls':
                    result = xls_plugin.Process(fp=file_path, ole_path=ole_path)
                elif extension == 'docx':
                    result = docx_plugin.Process(fp=file_path, ole_path=ole_path)
                elif extension == 'pptx':
                    result = pptx_plugin.Process(fp=file_path, ole_path=ole_path)
                elif extension == 'xlsx':
                    result = xlsx_plugin.Process(fp=file_path, ole_path=ole_path)
                elif extension == 'pdf':
                    result = pdf_plugin.Process(fp=file_path, ole_path=ole_path)
            except Exception as e:
                # print("Error : " + str(e))
                error_count += 1
                continue

            result.case_id = configuration.case_id
            result.evdnc_id = configuration.evidence_id
            result.download_path = file_path
            result.full_path = document_path  # 이미지 내 full_path
            result.path_with_ext = document_path  # 이미지 내 full_path
            result.parent_full_path = document_path[:document_path.rfind('\\')]
            result.name = document[0]
            result.original_size = os.path.getsize(file_path)
            result.ole_path = ole_path
            result.content_size = len(result.content)

            result.mft_st_created_time = str(datetime.utcfromtimestamp(
                int(str(document[6]).zfill(11) + str(document[10]).zfill(7)) / 10000000 - 11644473600)).replace(' ',
                                                                                                                'T') + 'Z'
            result.mft_st_last_modified_time = str(datetime.utcfromtimestamp(
                int(str(document[4]).zfill(11) + str(document[8]).zfill(7)) / 10000000 - 11644473600)).replace(' ',
                                                                                                               'T') + 'Z'
            result.mft_st_last_accessed_time = str(datetime.utcfromtimestamp(
                int(str(document[5]).zfill(11) + str(document[9]).zfill(7)) / 10000000 - 11644473600)).replace(' ',
                                                                                                               'T') + 'Z'
            result.mft_st_entry_modified_time = str(datetime.utcfromtimestamp(
                int(str(document[7]).zfill(11) + str(document[11]).zfill(7)) / 10000000 - 11644473600)).replace(' ',
                                                                                                                'T') + 'Z'
            result.mft_st_created_time = str(
                configuration.apply_time_zone(result.mft_st_created_time, knowledge_base.time_zone))
            result.mft_st_last_modified_time = str(
                configuration.apply_time_zone(result.mft_st_last_modified_time, knowledge_base.time_zone))
            result.mft_st_last_accessed_time = str(
                configuration.apply_time_zone(result.mft_st_last_accessed_time, knowledge_base.time_zone))
            result.mft_st_entry_modified_time = str(
                configuration.apply_time_zone(result.mft_st_entry_modified_time, knowledge_base.time_zone))

            result.mft_fn_created_time = str(datetime.utcfromtimestamp(
                int(str(document[14]).zfill(11) + str(document[18]).zfill(7)) / 10000000 - 11644473600)).replace(' ',
                                                                                                                 'T') + 'Z'
            result.mft_fn_last_modified_time = str(datetime.utcfromtimestamp(
                int(str(document[12]).zfill(11) + str(document[16]).zfill(7)) / 10000000 - 11644473600)).replace(' ',
                                                                                                                 'T') + 'Z'
            result.mft_fn_last_accessed_time = str(datetime.utcfromtimestamp(
                int(str(document[13]).zfill(11) + str(document[17]).zfill(7)) / 10000000 - 11644473600)).replace(' ',
                                                                                                                 'T') + 'Z'
            result.mft_fn_entry_modified_time = str(datetime.utcfromtimestamp(
                int(str(document[15]).zfill(11) + str(document[19]).zfill(7)) / 10000000 - 11644473600)).replace(' ',
                                                                                                                 'T') + 'Z'
            result.mft_fn_created_time = str(
                configuration.apply_time_zone(result.mft_fn_created_time, knowledge_base.time_zone))
            result.mft_fn_last_modified_time = str(
                configuration.apply_time_zone(result.mft_fn_last_modified_time, knowledge_base.time_zone))
            result.mft_fn_last_accessed_time = str(
                configuration.apply_time_zone(result.mft_fn_last_accessed_time, knowledge_base.time_zone))
            result.mft_fn_entry_modified_time = str(
                configuration.apply_time_zone(result.mft_fn_entry_modified_time, knowledge_base.time_zone))

            result.is_downloaded = 1 if document_path in zone_list else 0  # check Zone.Identifier, 1 = True, 0 = False
            result.is_copied = 1 if int(str(document[4]).zfill(11) + str(document[8]).zfill(7)) < int(
                str(document[6]).zfill(11) + str(document[10]).zfill(
                    7)) else 0  # check Mtime > Ctime, 1 = True, 0 = False

            # is_created

            result.is_created = 0
            try:
                if result.createdtime != 'None' and result.createdtime != '' and result.createdtime is not None:
                    if datetime.fromisoformat(result.createdtime.replace('Z', '')) > datetime.fromisoformat(
                            result.mft_st_created_time.split('+')[0]) == True:
                        result.is_created = 1
            except:
                pass

            rsid_list = []

            # RSID
            result.rsid = ""
            ext = os.path.splitext(file_path)[-1]
            if ext == '.docx':
                try:
                    zfile = zipfile.ZipFile(file_path)

                    for a in zfile.filelist:
                        if 'word/settings.xml' in a.filename:
                            form = zfile.read(a)
                            xmlroot = ET.fromstring(form)
                            for i in xmlroot:
                                if 'rsid' in i.tag:
                                    for rsid in i:
                                        rsid_list.append(rsid.attrib.get(
                                            "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}val"))
                except BadZipFile:
                    continue

            if configuration.standalone_check:
                if result.has_content:
                    result.has_content = 1
                else:
                    result.has_content = 0

                if result.has_metadata:
                    result.has_metadata = 1
                else:
                    result.has_metadata = 0

                if result.is_damaged:
                    result.is_damaged = 1
                else:
                    result.is_damaged = 0
                insert_document.append(tuple(
                    [par_id, configuration.case_id, configuration.evidence_id, result.author, result.case_name,
                     result.category, result.comment, result.company, result.content, result.content_size,
                     result.createdtime, result.creation_time, result.creator, result.date, result.doc_id,
                     result.doc_type, result.doc_type_sub, result.download_path, result.evdnc_name,
                     result.exclude_user_id, result.explanation, result.ext, result.fail_code, result.full_path,
                     result.has_content, result.has_exif, result.has_metadata, result.id, result.is_damaged,
                     result.is_fail, result.last_access_time, result.last_written_time, result.lastprintedtime,
                     result.lastsavedby, result.lastsavedtime, result.manager, result.name, result.ole_path,
                     result.original_size, result.parent_full_path, result.path_with_ext, result.programname,
                     result.revisionnumber, result.sha1_hash, result.subject, result.tags, result.title,
                     result.totaltime, result.trapped, result.version, result.work_dir, result.mft_st_created_time,
                     result.mft_st_last_modified_time, result.mft_st_last_accessed_time,
                     result.mft_st_entry_modified_time, result.mft_fn_created_time, result.mft_fn_last_modified_time,
                     result.mft_fn_last_accessed_time, result.mft_fn_entry_modified_time, result.is_downloaded,
                     result.is_copied, result.is_created, ''.join(rsid_list)]))

            else:
                try:
                    es.index(index=_index_name, doc_type=_type_name, body=result.__dict__)
                except Exception as e:
                    # print(f"Error : {str(e)}")
                    continue
        if configuration.standalone_check:
            query = "Insert into lv1_file_document values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, " \
                    "%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, " \
                    "%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s);"
            configuration.cursor.bulk_execute(query, insert_document)
            # print(f"Total Count : {total_count}, Error Count : {error_count}")

manager.ModulesManager.RegisterModule(DEFAConnector)
