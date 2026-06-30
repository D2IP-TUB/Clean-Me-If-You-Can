import base64
import string
import httplib2
from zlib import compress
from os import path, makedirs

def deflate_and_encode(plantuml_text):
    """对 PlantUML 文本进行 zlib 压缩并编码，以便于在 PlantUML 服务器上使用"""
    # 创建字节转换表
    maketrans = bytes.maketrans
    # PlantUML 服务器所使用的自定义字母表
    plantuml_alphabet = string.digits + string.ascii_uppercase + string.ascii_lowercase + '-_'
    # 标准 Base64 字母表
    base64_alphabet = string.ascii_uppercase + string.ascii_lowercase + string.digits + '+/'
    # 将 Base64 字母表转换为 PlantUML 字母表
    b64_to_plantuml = maketrans(base64_alphabet.encode('utf-8'), plantuml_alphabet.encode('utf-8'))
    # 对 PlantUML 文本进行 zlib 压缩
    zlibbed_str = compress(plantuml_text.encode('utf-8'))
    # 移除 zlib 压缩字符串的头两个字节和末尾四个字节（这部分是 zlib 特定的格式）
    compressed_string = zlibbed_str[2:-4]
    # 对压缩后的字符串进行 Base64 编码并转换为 PlantUML 所需的字母表
    return base64.b64encode(compressed_string).translate(b64_to_plantuml).decode('utf-8')

class PlantUML():
    def __init__(self):
        """PlantUML 类的初始化方法"""
        # 错误处理类
        self.HttpLib2Error = httplib2.HttpLib2Error
        # PlantUML 服务器 URL
        self.url = 'http://www.plantuml.com/plantuml/svg/'
        # 请求选项
        self.request_opts = {}
        # 创建 HTTP 客户端
        self.http = httplib2.Http(**{})

    def process_file(self, filename, outfile=None, directory=''):
        """读取包含 PlantUML 文本的文件并处理生成图像"""
        # 如果指定了目录且目录不存在，则创建目录
        if directory and not path.exists(directory):
            makedirs(directory)
        # 读取文件内容
        data = open(filename, encoding='utf-8').read()
        # 处理文件内容
        self._process(data, filename, outfile, directory)

    def process_str(self, plantuml_text, filename=None, outfile=None, directory=''):
        """直接处理 PlantUML 文本字符串并生成图像"""
        # 如果没有指定文件名，使用默认文件名
        if filename is None:
            filename = 'CleanerPlantuml.svg'
        # 处理 PlantUML 文本
        self._process(plantuml_text, filename, outfile, directory)

    def _process(self, plantuml_text, filename, outfile, directory):
        """内部方法，处理 PlantUML 文本并生成图像"""
        # 如果没有指定输出文件名，生成默认输出文件名
        if outfile is None:
            outfile = path.splitext(filename)[0] + '.svg'
        # 如果指定了目录且目录不存在，则创建目录
        if directory and not path.exists(directory):
            makedirs(directory)
        # 生成请求 URL
        url = self.url + deflate_and_encode(plantuml_text)
        try:
            # 发出 HTTP 请求以获取生成的图像
            response, content = self.http.request(url, **self.request_opts)
            # 将图像内容写入文件
            out = open(path.join(directory, outfile), 'wb')
            out.write(content)
            out.close()
        except:  # 捕获任何异常，例如网络问题
            return None