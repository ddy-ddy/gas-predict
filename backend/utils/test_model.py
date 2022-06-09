import torch
from backend.utils import args as ag
from backend.utils.utils import Painter
from backend.utils.model import GIN
from tqdm import tqdm
import pickle
from backend.utils import PYG_data


class Test_model:
    def __init__(self, dataset):
        # 读取参数
        self.args = ag.Args_parser("GIN").args
        if self.args.cuda and torch.cuda.is_available():
            torch.cuda.manual_seed(self.args.seed)
            torch.cuda.manual_seed_all(seed=self.args.seed)
            torch.manual_seed(self.args.seed)
        else:
            self.args.cuda = False
            self.args.device = torch.device("cpu")
            torch.manual_seed(self.args.seed)

        self.checkpoint_files_path = self.args.checkpoint_path
        self.dataset = dataset

        # 初始化模型
        output_dim = self.dataset.get(0).y.shape[0]
        input_dim = self.dataset.get(0).x.shape[1]
        self.model = GIN(num_layers=self.args.num_gin_layers, num_mlp_layers=self.args.num_mlp_layers,
                         hidden_dim=self.args.hidden,
                         input_dim=input_dim, output_dim=output_dim,
                         learn_eps=self.args.learn_eps, graph_pooling_type=self.args.graph_pooling_type,
                         neighbor_pooling_type=self.args.neighbor_pooling_type)

        if self.args.cuda:
            self.model = self.model.cuda()

        # 读取预训练参数
        if self.args.cuda:
            self.model.load_state_dict(torch.load("{}{}.pt".format(self.checkpoint_files_path, output_dim)))
        else:
            self.model.load_state_dict(torch.load("{}{}.pt".format(self.checkpoint_files_path, output_dim),
                                                  map_location=torch.device('cpu')))
        self.model.eval()

    def main(self):
        addFunSig_list = []
        pre_list = []
        dataLoader = self.dataset.test_dataset

        test_bar = tqdm(range(len(dataLoader)), unit='batch', position=4)

        for pos, data in zip(test_bar, dataLoader):
            # input data
            data.to(self.args.device)
            output = self.model(data.x, data.edge_index, data.batch)
            output = torch.exp(output)

            # draw info
            pre_list.extend(output.cpu())
            addFunSig_list.extend(data["addFunSig"])
            test_bar.set_description('test-')

        # # heatMap图像绘制与存储
        # painter = Painter(fig_output_path=self.args.png_output_path)
        # painter.draw_heatmap(outputs=pre_list, addFunSig_list=addFunSig_list)

        pickle.dump(dict(zip(addFunSig_list, pre_list)), open(self.args.output_file, "wb"))
        return addFunSig_list, pre_list


if __name__ == '__main__':
    dataset = PYG_data.GasPredictorDataset(name="500-1")
    test_model = Test_model(dataset)
    test_model.main()
