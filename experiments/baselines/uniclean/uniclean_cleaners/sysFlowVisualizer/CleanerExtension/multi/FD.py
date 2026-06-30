from collections import Counter

import numpy as np

from SampleScrubber.cleaner_model import CleanerModel


class FunctionalDependency(CleanerModel):

    def __init__(self, source, target):

        self.source = source
        self.target = target
        self.domain = set(source + target)
        self.fixValueRules = {}
        self.msg = 'FD:(source_attr: %s, target_attr: %s)' % (self.source, self.target)

    def __str__(self):
        return self.msg

    def _quality(self, df):
        N = df.shape[0]
        kv = {}
        normalization = 0
        for i in range(N):
            s = tuple(df[self.source].iloc[i, :])
            t = tuple(df[self.target].iloc[i, :])
            if s in kv:
                kv[s].append(t)
            else:
                kv[s] = [t]
        qfn_a = np.zeros((N,))
        for i in range(N):
            s = tuple(df[self.source].iloc[i, :])
            normalization = len(kv[s])
            count = Counter(kv[s])
            dic = dict(count)
            if (len(dic.keys()) == 1):
                qfn_a[i] = 0;
                continue;
            qfn_a[i] = 1 - float(dic[tuple(df[self.target].iloc[i, :])]) / normalization

        return qfn_a
