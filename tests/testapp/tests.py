from difflib import SequenceMatcher
from django import template
from django.conf import settings
from django.template.loader import render_to_string
from unittest import TestCase
import os
import subprocess
from sekizai.context import SekizaiContext
from sekizai.filters.css import DIR

def _is_installed(command):
    return subprocess.call(['which', command]) == 0

def clean_css(func):
    def _wrapped(*args, **kwargs):
        ret = func(*args, **kwargs)
        os.system('rm -Rf %s' % DIR)
        os.system('mkdir %s' % DIR)
    _wrapped.__name__ = func.__name__
    return _wrapped

class BitDiffResult(object):
    def __init__(self, status, message):
        self.status = status
        self.message = message


class BitDiff(object):
    def __init__(self, expected):
        self.expected = [unicode(bit) for bit in expected]
        
    def test(self, result):
        if self.expected == result:
            return BitDiffResult(True, "success")
        else: # pragma: no cover
            longest = max([len(x) for x in self.expected] + [len(x) for x in result] + [len('Expected')])
            sm = SequenceMatcher()
            sm.set_seqs(self.expected, result)
            matches = sm.get_matching_blocks()
            lasta = 0
            lastb = 0
            data = []
            for match in matches:
                unmatcheda = self.expected[lasta:match.a]
                unmatchedb = result[lastb:match.b]
                unmatchedlen = max([len(unmatcheda), len(unmatchedb)])
                unmatcheda += ['' for x in range(unmatchedlen)]
                unmatchedb += ['' for x in range(unmatchedlen)]
                for i in range(unmatchedlen):
                    data.append((False, unmatcheda[i], unmatchedb[i]))
                for i in range(match.size):
                    data.append((True, self.expected[match.a + i], result[match.b + i]))
                lasta = match.a + match.size
                lastb = match.b + match.size
            padlen = (longest - len('Expected'))
            padding = ' ' * padlen
            line1 = '-' * padlen
            line2 = '-' * (longest - len('Result'))
            msg = '\nExpected%s |   | Result' % padding
            msg += '\n--------%s-|---|-------%s' % (line1, line2)
            for success, a, b in data:
                pad = ' ' * (longest - len(a))
                if success:
                    msg += '\n%s%s |   | %s' % (a, pad, b)
                else:
                    msg += '\n%s%s | ! | %s' % (a, pad, b)
            return BitDiffResult(False, msg)


class SekizaiTestCase(TestCase):
    def _render(self, tpl, ctx={}, ctxinstance=SekizaiContext):
        return render_to_string(tpl, ctxinstance(ctx))
        
    def _test(self, tpl, res, ctx={}):
        """
        Helper method to render template and compare it's bits
        """
        rendered = self._render(tpl, ctx)
        bits = [bit for bit in [bit.strip('\n') for bit in rendered.split('\n')] if bit]
        differ = BitDiff(res)
        result = differ.test(bits)
        self.assertTrue(result.status, result.message)
        return rendered
    
    def _load_filter(self, import_path, namespace, configs={}):
        from sekizai.filters.base import Namespace, registry
        from sekizai.utils import load_filter
        filter_class = load_filter(import_path)
        registry.namespaces[namespace] = Namespace(True, [filter_class], configs)
        return registry, filter_class
        
    def test_01_basic(self):
        """
        Basic dual block testing
        """
        bits = ['my css file', 'some content', 'more content', 
            'final content', 'my js file']
        self._test('basic.html', bits)

    def test_02_named_end(self):
        """
        Testing with named endaddblock
        """
        bits = ["mycontent"]
        self._test('named_end.html', bits)

    def test_03_eat(self):
        """
        Testing that content get's eaten if no render_blocks is available
        """
        bits = ["mycontent"]
        self._test("eat.html", bits)
        
    def test_04_fail(self):
        """
        Test that the template tags properly fail if not used with either 
        SekizaiContext or the context processor.
        """
        self.assertRaises(template.TemplateSyntaxError, self._render, 'basic.html', {}, template.Context)
        
    def test_05_template_inheritance(self):
        """
        Test that (complex) template inheritances work properly
        """
        bits = ["head start", "some css file", "head end", "include start",
                "inc add js", "include end", "block main start", "extinc",
                "block main end", "body pre-end", "inc js file", "body end"]
        self._test("inherit/extend.html", bits)
        
    def test_06_namespace_isolation(self):
        """
        Tests that namespace isolation works
        """
        bits = ["the same file", "the same file"]
        self._test('namespaces.html', bits)
        
    def test_07_variable_namespaces(self):
        """
        Tests variables and filtered variables as block names.
        """
        bits = ["file one", "file two"]
        self._test('variables.html', bits, {'blockname': 'one'})
        
    def test_08_yui(self):
        if not _is_installed('yui-compressor'): # pragma: no cover 
            return
        registry, filter_class = self._load_filter('sekizai.filters.javascript.JavascriptMinfier', 'js')
        self.assertEqual(len(list(registry.get_filters('js'))), 2)
        js = """<script type='text/javascript'>var a = 1;

        var b = a + 2;</script>"""
        self.assertNotEqual(js, filter_class().postprocess(js, 'js'))
        bits = ['<script type="text/javascript">var a=1;var b=a+2;</script>',
                '<script type="text/javascript" src="somefile.js"></script>']
        self._test('yui.html', bits)

    def test_09_template_errors(self):
        """
        Tests that template syntax errors are raised properly in templates
        rendered by sekizai tags
        """
        self.assertRaises(template.TemplateSyntaxError, self._render, 'errors/failadd.html')
        self.assertRaises(template.TemplateSyntaxError, self._render, 'errors/failrender.html')
        self.assertRaises(template.TemplateSyntaxError, self._render, 'errors/failinc.html')
        self.assertRaises(template.TemplateSyntaxError, self._render, 'errors/failbase.html')
        self.assertRaises(template.TemplateSyntaxError, self._render, 'errors/failbase2.html')

    @clean_css
    def test_10_css_to_file(self):
        import hashlib
        raw_css = 'body { color: red; }'
        filename = '%s.css' % hashlib.sha1(raw_css).hexdigest()
        filepath = os.path.join(DIR, filename)
        fileurl = os.path.relpath(filepath, settings.MEDIA_ROOT)
        link = u'<link rel="stylesheet" href="%s%s" />' % (settings.MEDIA_URL, fileurl)
        registry, filter_class = self._load_filter('sekizai.filters.css.CSSInlineToFileFilter', 'css-to-file')
        self.assertEqual(len(list(registry.get_filters('css-to-file'))), 2)
        css = '<style type="text/css">body { color: red; }</style>'
        self.assertNotEqual(css, filter_class().postprocess(css, 'css-to-file'))
        self._test('css.html', [link])
        # check file contents
        f = open(filepath, 'r')
        data = f.read()
        f.close()
        self.assertEqual(data, raw_css)
        
    @clean_css
    def test_11_css_onefile(self):
        import hashlib
        raw_css = """body { background: red; }
div { color: red; }"""
        registry, filter_class = self._load_filter('sekizai.filters.css.CSSSingleFileFilter', 'css-onefile')
        self.assertEqual(len(list(registry.get_filters('css-onefile'))), 2)
        css = """<link rel="stylesheet" href="/media/css/one.css" /> 
<link rel="stylesheet" href="/media/css/two.css" />"""
        self.assertNotEqual(css, filter_class().postprocess(css, 'css-onefile'))
        filename = '%s.css' % hashlib.sha1('/media/css/one.css/media/css/two.css').hexdigest()
        filepath = os.path.join(DIR, filename)
        fileurl = os.path.relpath(filepath, settings.MEDIA_ROOT)
        link = u'<link rel="stylesheet" href="%s%s" />' % (settings.MEDIA_URL, fileurl)
        self._test('css2.html', [link])
        # check file contents
        f = open(filepath, 'r')
        data = f.read()
        f.close()
        self.assertEqual(data, raw_css)
        # check that file get's rebuilt if we change it's contents
        fpath = os.path.join(os.path.abspath(os.path.dirname(__file__)), 'media/css/one.css')
        f = open(fpath)
        old = f.read()
        f.close()
        try:
            new = "body { background: blue; }"
            f = open(fpath, 'w')
            f.write(new)
            f.close()
            self._test('css2.html', [link])
            f = open(filepath, 'r')
            newdata = f.read()
            f.close()
            self.assertNotEqual(data, newdata)
        finally:
            f = open(fpath, 'w')
            f.write(old)
            f.close()
            
    def test_12_registry(self):
        SEKIZAI_FILTERS = {
            'css-onefile': {
                'filters': ['sekizai.filters.css.CSSSingleFileFilter'],
            },
        }
        from sekizai.filters.base import Registry
        r = Registry()
        r.init(SEKIZAI_FILTERS)
        self.assertEqual(len(list(r.get_filters('css-onefile'))), 2)
        r.add('css-onefile', 'sekizai.filters.django_filters.SpacelessFilter')
        self.assertEqual(len(list(r.get_filters('css-onefile'))), 3)
        
    def test_13_spaceless(self):
        registry, filter_class = self._load_filter('sekizai.filters.django_filters.SpacelessFilter', 'spaceless')
        self.assertEqual(len(list(registry.get_filters('spaceless'))), 2)
        bits = ["<strong>Strong</strong>", "<i>oblique</i>"]
        html = "\n".join(bits)
        self.assertNotEqual(html, filter_class().postprocess(html, 'spaceless'))
        self._test('spaceless.html', [''.join(bits)])