class Screenshot(object):

    def __init__(self, img):
        img = Screenshot.__convert_in_pil_image(img)
        self.__img = Screenshot.__crop_image(img)

    def is_different_from(self, other_screenshot, threshold_percentage=0):
        if not isinstance(other_screenshot, Screenshot):
            raise Exception("other_screenshot must be an instance of Screenshot")
        if self.__img.size != other_screenshot.__img.size:
            raise Exception("the images must have the same size")
        img1 = Screenshot.__convert_to_gray_scale(self.__img)
        img2 = Screenshot.__convert_to_gray_scale(other_screenshot.__img)
        height = img1.height
        width = img1.width
        import numpy
        img1 = numpy.asarray(img1)
        img2 = numpy.asarray(img2)
        return numpy.count_nonzero(img1 - img2) > height * width * threshold_percentage / 100

    def save_img_on_file(self, file_name):
        self.__img.save(file_name, "png")

    @staticmethod
    def __crop_image(img):
        return img.crop((0, img.height * 0.04, img.width, 1776))

    @staticmethod
    def __convert_to_gray_scale(img):
        return img.convert("L")

    @staticmethod
    def __convert_in_pil_image(img):
        import io
        from PIL import Image
        img = Image.open(io.BytesIO(img))
        import numpy
        tmp = numpy.array(img)
        img.close()
        img = Image.fromarray(tmp)
        return img
