class View(object):

    def __init__(self, views):
        self.views = views

    @staticmethod
    def filter_views(views):
        result = []
        do_not_consider = ["children", "temp_id", "child_count", "parent", "view_str", "signature",
                           "content_free_signature"]
        tmp = []
        for view in views:
            tmp.append(view.copy())
        for view in tmp:
            for elem in do_not_consider:
                del view[elem]
            if view not in result:
                result.append(view)
        return result

    def is_different_from(self, other):
        if not isinstance(other, View):
            raise Exception("other is not a View object")
        before = View.filter_views(self.views)
        after = View.filter_views(other.views)
        if len(before) != len(after):
            return True
        for i in range(0, len(before)):
            dict_before = before[i]
            dict_after = after[i]
            for key in before[i].keys():
                if dict_before[key] != dict_after[key]:
                    return True
        return False