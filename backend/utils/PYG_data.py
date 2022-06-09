import torch
from torch_geometric.data import Data, InMemoryDataset
import dill
import os.path as osp
from sklearn.preprocessing import normalize
from torch_geometric.data import DataLoader


class GasPredictorDataset(InMemoryDataset):

    def __init__(self, name="500-1", root='../tmp_files/cfg_build/dataset/', batch_size=32):
        # prepare data arguments
        self.name = name
        self.batch_size = batch_size
        self.intervalNum = int(name.split("-")[0])
        super(GasPredictorDataset, self).__init__(root, transform=self.transform_dgl_data_to_pyg)
        self.data, self.slices = torch.load(self.processed_paths[0])
        self.test_dataset = DataLoader([self.get(idx=idx) for idx in range(len(self))], batch_size=self.batch_size)

    @property
    def raw_file_names(self):
        return 'graph_data_dic.pkl'

    @property
    def raw_dir(self):
        return osp.join(self.root, 'raw')

    @property
    def processed_dir(self):
        return osp.join(self.root, self.name, 'processed')

    @property
    def processed_file_names(self):
        return f'{self.name}'

    def download(self):
        pass

    def process(self):
        data_list = []

        target_raw_path = [raw_path for raw_path in self.raw_paths][0]
        # read_dgl_graph
        raw_datas = dill.load(open(target_raw_path, "rb"))

        # transform data and mark CFG
        for dgl_data in raw_datas.items():
            data = self.transform(dgl_data)
            data_list.append(data)

        data, slices = self.collate(data_list)
        torch.save((data, slices), self.processed_paths[0])

    def __repr__(self):
        return '{}({})'.format(self.name, len(self))

    def __getitem__(self, key):
        return

    def transform_dgl_data_to_pyg(self, dgl_data):
        addFunSig = dgl_data[0]
        dgl_graph = dgl_data[1]

        # 全0的label
        label = torch.tensor([0.] * self.intervalNum, dtype=torch.float32)
        edge_index = torch.tensor(list(map(lambda x: x.tolist(), list(dgl_graph.edges()))), dtype=torch.long)
        # 节点的特征
        graph_nodes_feature = dict(dgl_graph.ndata)
        opCode_feature = graph_nodes_feature['opCode_feature']
        strengthen_feature = graph_nodes_feature['strengthen_feature']
        spOPcode_feature = graph_nodes_feature['spOPcode_feature']
        # 用于子图解释对应原图的节点标记
        node_add_list = list(map(lambda x: hex(x), graph_nodes_feature['node_add_list'].tolist()))

        # l2范数标准化，分特征字段进行标准化
        opCode_feature = torch.tensor(normalize(opCode_feature), dtype=torch.float32)
        spOPcode_feature = torch.tensor(normalize(spOPcode_feature), dtype=torch.float32)
        strengthen_feature = torch.tensor(normalize(strengthen_feature), dtype=torch.float32)

        nodes_feature = torch.cat([opCode_feature, strengthen_feature, spOPcode_feature], dim=1)

        data = Data(x=nodes_feature, edge_index=edge_index, y=label,
                    __num_nodes__=dgl_graph.num_nodes(), addFunSig=addFunSig, node_add_list=node_add_list)
        return data


if __name__ == '__main__':
    dataset = PYG_data.GasPredictorDataset(name="500-1")
    gp_data = GasPredictorDataset(dataset)
