import torch
import torch.nn as nn
import torch.nn.functional as F


class MFM(nn.Module):
    """docstring for MFM"""
    def __init__(self,
                 in_channels,
                 out_channels,
                 kernel_size=3,
                 padding=1,
                 stride=1):
        super().__init__()
        self.filter = nn.Sequential(
            nn.Conv2d(in_channels,
                      2 * out_channels,
                      kernel_size=kernel_size,
                      padding=padding,
                      stride=stride))
        self.norm = nn.BatchNorm2d(out_channels)

    def forward(self, x):
        x = self.filter(x)
        low, up = torch.chunk(x, 2, 1)
        return self.norm(torch.max(low, up))


class MFMGroup(nn.Module):
    """docstring for MFMGroup"""
    def __init__(self,
                 in_channels,
                 out_channels,
                 kernel_size=3,
                 padding=1,
                 stride=1):
        super().__init__()
        self.group = nn.Sequential(
            MFM(in_channels=in_channels,
                out_channels=out_channels,
                kernel_size=1,
                padding=0,
                stride=1),
            MFM(in_channels=out_channels,
                out_channels=out_channels,
                kernel_size=kernel_size,
                padding=padding,
                stride=stride))

    def forward(self, x):
        return self.group(x)


class LightCNN(nn.Module):
    def __init__(self, inputdim, outputdim, **kwargs):
        super().__init__()
        self._filtersizes = kwargs.get('filtersizes', [3, 3, 3, 3, 3, 3, 3])
        self._filter = [1] + kwargs.get('filter',
                                        [16, 48, 96, 128, 256, 512, 1024])
        self._pooling = kwargs.get('pooling', [2, 2, 2, 2, 2, (1, 2)])
        net = nn.ModuleList()
        for nl, (h0, h1, filtersize, poolingsize) in enumerate(
                zip(self._filter, self._filter, self._filtersizes,
                    self._pooling)):
            if nl == 0:
                mfmtype = "MFM"
            else:
                mfmtype = "MFMGroup"
            net.append(globals()[mfmtype](
                in_channels=h0,
                out_channels=h1,
                kernel_size=filtersize,
                padding=int(filtersize) // 2,
                stride=1,
            ))
            net.append(nn.MaxPool2d(kernel_size=poolingsize))
            # Only dropout at last layer before GRU
            if nl == (len(self._filter) - 2):
                net.append(nn.Dropout(0.3))
        self.network = nn.Sequential(*net)
        with torch.no_grad():
            feature_output = self.network(torch.randn(1, 1, 300, inputdim)).shape
            feature_output = feature_output[-1] * feature_output[1]

        self.timepool = nn.AdaptiveAvgPool2d(1)
        self.outputlayer = nn.Sequential(
            nn.Conv1d(feature_output, outputdim, kernel_size=1, groups=1))

        self.network.apply(init_weights)
        self.outputlayer.apply(init_weights)

    def forward(self, x):
        x = x.unsqueeze(1)
        x = self.network(x)
        x = self.timepool(x).flatten(-2)
        return self.outputlayer(x)


def init_weights(m):
    if isinstance(m, (nn.Conv2d, nn.Conv1d)):
        nn.init.kaiming_normal_(m.weight)
        if m.bias is not None:
            nn.init.constant_(m.bias, 0)
    elif isinstance(m, nn.BatchNorm2d):
        nn.init.constant_(m.weight, 1)
        if m.bias is not None:
            nn.init.constant_(m.bias, 0)
    if isinstance(m, nn.Linear):
        nn.init.kaiming_uniform_(m.weight)
        if m.bias is not None:
            nn.init.constant_(m.bias, 0)