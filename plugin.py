import os, shutil, random, threading, urllib
from urlparse import urlparse

if os.path.sep == '/':
    quote = urllib.quote
    unquote = urllib.unquote_plus
else:
    quote = lambda x: urllib.quote(x.replace(os.path.sep, '/'))
    unquote = lambda x: urllib.unquote_plus(x).replace('/', os.path.sep)

def GetPlugin(name):
    module_name = '.'.join(['plugins', name, name])
    module = __import__(module_name, globals(), locals(), name)
    plugin = getattr(module, module.CLASS_NAME)()
    return plugin

class Plugin(object):

    random_lock = threading.Lock()

    CONTENT_TYPE = ''

    def __new__(cls, *args, **kwds):
        it = cls.__dict__.get('__it__')
        if it is not None:
            return it
        cls.__it__ = it = object.__new__(cls)
        it.init(*args, **kwds)
        return it

    def init(self):
        pass

    def send_file(self, handler, container, name):
        o = urlparse("http://fake.host" + handler.path)
        path = unquote(o[2])
        handler.send_response(200)
        handler.end_headers()
        f = file(container['path'] + path[len(name)+1:], 'rb')
        shutil.copyfileobj(f, handler.wfile)

    def get_local_base_path(self, handler, query):

        subcname = query['Container'][0]
        container = handler.server.containers[subcname.split('/')[0]]

        return container['path']

    def get_local_path(self, handler, query):

        subcname = query['Container'][0]
        container = handler.server.containers[subcname.split('/')[0]]

        path = container['path']
        for folder in subcname.split('/')[1:]:
            if folder == '..':
                return False
            path = os.path.join(path, folder)
        return path

    def item_count(self, handler, query, cname, files):
        """Return only the desired portion of the list, as specified by 
           ItemCount, AnchorItem and AnchorOffset
        """
        totalFiles = len(files)
        index = 0

        if totalFiles and query.has_key('ItemCount'):
            count = int(query['ItemCount'][0])

            if query.has_key('AnchorItem'):
                bs = '/TiVoConnect?Command=QueryContainer&Container='
                local_base_path = self.get_local_base_path(handler, query)

                anchor = query['AnchorItem'][0]
                if anchor.startswith(bs):
                    anchor = anchor.replace(bs, '/')
                anchor = unquote(anchor)
                anchor = anchor.replace(os.path.sep + cname, local_base_path)
                anchor = os.path.normpath(anchor)

                try:
                    index = files.index(anchor)
                except ValueError:
                    print 'Anchor not found:', anchor  # just use index = 0

                if count > 0:
                    index += 1

                if query.has_key('AnchorOffset'):
                    index += int(query['AnchorOffset'][0])

                #foward count
                if count >= 0:
                    files = files[index:index + count]
                #backwards count
                else:
                    if index + count < 0:
                        count = -index
                    files = files[index + count:index]
                    index += count

            else:  # No AnchorItem

                if count >= 0:
                    files = files[:count]
                else:
                    index = count % len(files)
                    files = files[count:]

        return files, totalFiles, index

    def get_files(self, handler, query, filterFunction=None):
        subcname = query['Container'][0]
        cname = subcname.split('/')[0]
        path = self.get_local_path(handler, query)
        
        files = [ os.path.join(path, file) for file in os.listdir(path)]
        if query.get('Recurse',['No'])[0]  == 'Yes':
            for file in files:
                if os.path.isdir(file):
                    for new_file in os.listdir(file):
                        files.append( os.path.join(file, new_file) )

        file_type = query.get('Filter', [''])[0]
        if filterFunction:
            files = [file for file in files if filterFunction(file, file_type)]

        totalFiles = len(files)

        def dir_sort(x, y):
            xdir = os.path.isdir(os.path.join(path, x))
            ydir = os.path.isdir(os.path.join(path, y))

            if xdir == ydir:
                return name_sort(x, y)
            else:
                return ydir - xdir

        def name_sort(x, y):
            return cmp(x, y)

        if query.get('SortOrder',['Normal'])[0] == 'Random':
            seed = query.get('RandomSeed', ['1'])[0]
            self.random_lock.acquire()
            random.seed(seed)
            random.shuffle(files)
            self.random_lock.release()
        else:
            files.sort(dir_sort)

        # Trim the list
        return self.item_count(handler, query, cname, files)
