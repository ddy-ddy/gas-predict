import argparse
import torch


def str2bool(str0):
    return True if str0.lower() == 'true' else False


class Args_parser:
    def __init__(self, description):
        self.parser = argparse.ArgumentParser(description)
        self.args = None
        self._parser()

    def _parser(self):
        self.parser.add_argument('--seed', type=int, default=72, help='Random seed.')
        self.parser.add_argument('--hidden', type=int, default=550, help='Number of hidden units.')
        self.parser.add_argument('--num_gin_layers', type=int, default=5, help='Number of GIN layers.')
        self.parser.add_argument('--num_mlp_layers', type=int, default=3, help='Number of MLP layers.')
        self.parser.add_argument('--learn_eps', type=str2bool, default=False, help='learn the epsilon weighting')
        self.parser.add_argument('--graph_pooling_type', default='sum',
                                 help='How to aggregate entire nodes in a graph (sum, mean or max).')
        self.parser.add_argument('--neighbor_pooling_type', default='add',
                                 help='How to aggregate neighbors (add, mean, or max)')
        self.parser.add_argument('--output_file', type=str, default="../output/output.pkl", help='output file')
        self.parser.add_argument('--checkpoint_path', default="../checkpoint_pkls/", help='Checkpoint_path.')
        self.parser.add_argument('--png_output_path', type=str, default="../output/heatMaps/", help='Heatmaps path.')
        self.parser.add_argument('--output_path', type=str, default="../output/",
                                 help='output png graph path.')
        self.parser.add_argument('--no-cuda', default=False, help='Disables CUDA training.')
        self.parser.add_argument('--device', type=torch.device, default=torch.device("cpu"), help='Data device.')

        self.args = self.parser.parse_args()

        # 设置使用的运算设备，只有在no_cuda为false以及gpu可用时才使用gpu
        self.args.cuda = not self.args.no_cuda and torch.cuda.is_available()
        if self.args.cuda:
            self.args.device = torch.device("cuda:0")
        else:
            self.args.device = torch.device("cpu")
