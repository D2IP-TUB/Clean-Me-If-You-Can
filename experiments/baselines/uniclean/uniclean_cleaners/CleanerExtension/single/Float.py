import numpy as np

from SampleScrubber.cleaner_model import ParametrizedLanguage
from SampleScrubber.cleaner.single import Single
from SampleScrubber.ModuleTest.SparkClean.spark_rule_model import formatString


class Float(Single):
    def __init__(self, domain, nrange=None):
        """float constructor

        Positional arguments:
        attr -- an attribute name
        nrange -- the range of allowed values
        """
        if nrange is None:
            nrange = [-np.inf, np.inf]
        self.attr = domain
        self.range = nrange

        def floatPatternCheck(x):
            if x == None or isinstance(x, float):
                return True
            else:
                return False

        super(Float, self).__init__(domain, lambda x: floatPatternCheck(x))

    def preProcess(self):
        floatInstance = self

        class PreLanguage(ParametrizedLanguage):
            paramDescriptor = {'domain': ParametrizedLanguage.DOMAIN,
                               'format': ParametrizedLanguage.FORMAT,
                               'opinformation': ParametrizedLanguage.OPINFORMATION,
                               }

            def __init__(self, floatInstance):
                domain = floatInstance.domain
                format = floatInstance.format
                opinformation = str(floatInstance)

                def fn(df, domain=domain, r=format):

                    def __internal(row):
                        try:
                            value = float(row[domain])
                            if r[0] <= value <= r[1]:
                                return value
                            else:
                                return None
                        except:
                            return None

                    df[domain] = df.apply(lambda row: __internal(row), axis=1)
                    return df

                self.name = 'df = numparse(df,' + formatString(domain) + str(opinformation) + ')'
                self.provenance = [self]

                super(PreLanguage, self).__init__(fn, ['domain', 'format', 'opinformation'])

        return PreLanguage(floatInstance)
