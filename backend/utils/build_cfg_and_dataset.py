import datetime
import multiprocessing
import os
import time
import dill
import sys
import pickle
import glob

from backend.utils.utils import get_files_path_dic, write_error_info_to_text, process_bar
from backend.utils.Vandal_src import tac_cfg, dataflow, exporter
from backend.utils.Vandal_src.utils import embeding_nodes, modify_op_code_list, create_dgl_object

# 程序最大递归深度
sys.setrecursionlimit(1000000)
use_strengthen_vector = True
error_text_path = "../tmp_files/log_pkl/error_list.txt"


# 这个参数a不能删
def build_cfg(bytecode_file_path, tsv_output_dir, pkl_path, a):
    try:
        cfg = tac_cfg.TACGraph.from_bytecode(open(bytecode_file_path, "r", encoding="utf-8"))
        dataflow.analyse_graph(cfg)
        c.build_data_from_cfg(cfg, bytecode_file_path)
        pickle.dump(cfg, open(pkl_path + "cfg.pkl", "wb"))
        exporter.CFGTsvExporter(cfg).export(output_dir=tsv_output_dir)
        exporter.CFGDotExporter(cfg).export(pkl_path + "cfg.html")
    except Exception as e:
        print(e)
        sys.exit(1)


class DGL_Data_Builder:
    # 输出目录
    output_path = "../tmp_files/cfg_build/"
    # 超时设定
    time_out = 10000

    now_contract_name = ""
    now_funSig = ""
    graph_data_dic = {}

    def __init__(self):
        bytes_files_path = "../tmp_files/contracts_bytes/"
        self.file_path_dic = get_files_path_dic(bytes_files_path, min_file=0)

    def main(self):
        count = 0
        # 先按合约地址遍历，再按函数遍历
        for item in self.file_path_dic.items():
            # 进度条显示
            count += 1
            print("{}/{}".format(count, self.file_path_dic.__len__()))
            process_bar(count / self.file_path_dic.__len__())

            folder_path = item[0]
            funSig_list = item[1]
            self.now_contract_name = folder_path.split("/")[-1]

            """
            debug use
            if self.now_contract_name != "AirDrop":
                continue
            """

            for funSig in funSig_list:
                self.now_funSig = funSig.replace(".hex", "")
                bytes_file_path = "{}/{}".format(folder_path, funSig)
                tsv_output_path = "{}{}/{}/tsv_files/".format(self.output_path, self.now_contract_name, self.now_funSig)
                cfg_pkl_output_path = "{}{}/{}/".format(self.output_path, self.now_contract_name,
                                                        self.now_funSig)

                exitcode = self.get_hex_info_decompile(bytes_file_path=bytes_file_path,
                                                       tsv_files_path=tsv_output_path,
                                                       pkl_file_path=cfg_pkl_output_path)
                if exitcode != 0:
                    write_error_info_to_text(error_text_path,
                                             ":".join([self.now_contract_name, self.now_funSig,
                                                       "\texit code is not zero\n"]))

            # 把所有生成的dgl数据打包成一个字典，以pkl的形式保存
            dgl_data_path_list = glob.glob(self.output_path + "/**/dgl_graph.pkl", recursive=True)
            for file_path in dgl_data_path_list:
                tmp = file_path.split("/")
                contract_name, function_name = tmp[-3], tmp[-2]
                self.graph_data_dic["{}:{}".format(contract_name, function_name)] = pickle.load(open(file_path, "rb"))

            if not os.path.exists(self.output_path + "/dataset/raw/"):
                os.makedirs(self.output_path + "/dataset/raw/")
            dill.dump(self.graph_data_dic, open(self.output_path + "/dataset/raw/graph_data_dic.pkl", "wb"))

    # 以多进程的方法运行build_cfg函数获得CFG图，细节tsv信息文件保存到tsv_files_path目录下，CFG对象的二进制保存到cfg_pkl目录下
    def get_hex_info_decompile(self, bytes_file_path, tsv_files_path, pkl_file_path):
        # 为生成CFG图的函数开一个进程
        p = multiprocessing.Process(target=build_cfg, args=(bytes_file_path, tsv_files_path, pkl_file_path, "a"))
        p.start()
        start = datetime.datetime.now()
        while p.is_alive():
            time.sleep(0.1)
            now = datetime.datetime.now()
            if (now - start).seconds > self.time_out:
                p.kill()
        return p.exitcode

    def build_data_from_cfg(self, cfg, path):
        # 当前处理的合约信息
        tmp = path.split("/")
        self.now_contract_name = tmp[3]
        self.now_funSig = tmp[4].replace(".hex", "")

        # 如果CFG里面的public函数不为2（目标函数+fallback函数）,那么跳过此合约函数的CFG
        if cfg.function_extractor.public_functions.__len__() != 2:
            write_error_info_to_text(error_text_path, self.now_contract_name + ":" + self.now_funSig + "\tcfg error")
            return None

        dis_node_list = []
        # 判断选择函数的节点是否已经找齐
        find_all_flag = False
        for block in cfg.blocks:
            # 没有对应函数的节点，可能是选择函数也可能是Vandal没有找到对应函数的节点
            # 所以先筛选掉选择函数的节点后，全部归属到目标函数
            if (block.ident_suffix == "") and (not find_all_flag):
                continue
            elif "_F1" not in block.ident_suffix:
                find_all_flag = True
                dis_node_list.append(block)

        # 节点的地址到id的映射字典
        node_add2id_dic = {}
        node_count = 0
        # 节点特征列表
        nodes_op_codes_list = []

        for block in dis_node_list:
            node_add2id_dic[block.evm_ops[0].__str__().split(" ")[0]] = node_count  # 不能用tac_ops，要用evm_ops的第一个地址
            ori_op_codes_list = [op_code.__str__().split(" ", 1)[-1] for op_code in block.evm_ops]
            nodes_op_codes_list.append(modify_op_code_list(ori_op_codes_list))
            node_count += 1

        # 节点的变量使用字典，用于添加数据流的相关边
        graph = create_dgl_object(dis_node_list, node_add2id_dic)

        # 节点特征嵌入
        graph = embeding_nodes(graph, nodes_op_codes_list, list(node_add2id_dic.keys()))

        output_path = "{}{}/{}/".format(self.output_path, self.now_contract_name, self.now_funSig)
        if not os.path.exists(output_path):
            os.makedirs(output_path, exist_ok=True)

        dill.dump(graph, open(output_path + "dgl_graph.pkl", "wb"))


c = DGL_Data_Builder()
c.main()
