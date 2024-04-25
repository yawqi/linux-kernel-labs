# -*- coding: utf-8 -*-
"""
    sphinx.ext.ditaa
    ~~~~~~~~~~~~~~~~~~~~~~~~~
    Allow ditaa-formatted graphs to by included in Sphinx-generated
    documents inline.
    :copyright: Copyright 2017 by Yongping Guo
    :license: BSD, see LICENSE for details.
"""
from __future__ import print_function

import re, os
import codecs
import posixpath
from os import path
from math import ceil
from subprocess import Popen, PIPE
try:
    from hashlib import sha1 as sha
except ImportError:
    from sha import sha

from docutils import nodes
from docutils.parsers.rst import directives

from sphinx.errors import SphinxError
from sphinx.util.osutil import ensuredir, ENOENT, EPIPE
from sphinx.util import relative_uri
#from sphinx.util.compat import Directive
from docutils.parsers.rst import Directive

mapname_re = re.compile(r'<map id="(.*?)"')
svg_dim_re = re.compile(r'<svg\swidth="(\d+)pt"\sheight="(\d+)pt"', re.M)

class DitaaError(SphinxError):
    category = 'Ditaa error'


class ditaa(nodes.General, nodes.Element):
    pass

class Ditaa(directives.images.Image):
    """
    Directive to insert ditaa markup.
    """
    has_content = True
    required_arguments = 0
    optional_arguments = 0
    final_argument_whitespace = False
    option_spec = {
            # image parameter
            'name': directives.unchanged,
            'class': directives.unchanged,
            'alt': directives.unchanged,
            'title': directives.unchanged,
            'height': directives.unchanged,
            'width': directives.unchanged,
            'scale': directives.unchanged,
            'align': directives.unchanged,
            'target': directives.unchanged,
            'inline': directives.unchanged,
            # ditaa parameter
            '--no-antialias': directives.flag,
            '--background': directives.unchanged,
            '--no-antialias': directives.flag,
            '--no-separation': directives.flag,
            '--encoding': directives.unchanged,
            '--html': directives.flag,
            '--overwrite': directives.flag,
            '--round-corners': directives.flag,
            '--no-shadows': directives.flag,
            '--scale': directives.unchanged,
            '--transparent': directives.flag,
            '--tabs': directives.unchanged,
            '--fixed-slope': directives.flag,
    }

    def run(self):
        if self.arguments:
            print(self.arguments)
            document = self.state.document
            if self.content:
                return [document.reporter.warning(
                    'Ditaa directive cannot have both content and '
                    'a filename argument', line=self.lineno)]
            env = self.state.document.settings.env
            rel_filename, filename = env.relfn2path(self.arguments[0])
            env.note_dependency(rel_filename)
            try:
                fp = codecs.open(filename, 'r', 'utf-8')
                try:
                    dotcode = fp.read()
                finally:
                    fp.close()
            except (IOError, OSError):
                return [document.reporter.warning(
                    'External Ditaa file %r not found or reading '
                    'it failed' % filename, line=self.lineno)]
        else:
            dotcode = '\n'.join(self.content)
            if not dotcode.strip():
                return [self.state_machine.reporter.warning(
                    'Ignoring "ditaa" directive without content.',
                    line=self.lineno)]
        node = ditaa()
        node['code'] = dotcode
        node['options'] = []
        node['img_options'] = {}
        for k,v in self.options.items():
            if k[:2] == '--':
                node['options'].append(k)
                if v is not None:
                    node['options'].append(v)
            else:
                node['img_options'][k] = v
                #if v is not None:
                #    node['options'].append("%s" %(v))

        return [node]

def render_ditaa(app, code, options, format, prefix='ditaa'):
    """Render ditaa code into a PNG output file."""
    # ditaa expects UTF-8 by default
    code = code.encode('utf-8')
    hashkey = str(code) + str(options) + \
              str(app.builder.config.ditaa) + \
              str(app.builder.config.ditaa_args)
    infname = '%s-%s.%s' % (prefix, sha(hashkey.encode('utf-8')).hexdigest(), "ditaa")
    outfname = '%s-%s.%s' % (prefix, sha(hashkey.encode('utf-8')).hexdigest(), "png")

    rel_imgpath = (format == "html") and relative_uri(app.builder.env.docname, app.builder.imagedir) or ''
    infullfn = path.join(app.builder.outdir, app.builder.imagedir, infname)
    outrelfn = posixpath.join(relative_uri(app.builder.env.docname, app.builder.imagedir), outfname)
    outfullfn = path.join(app.builder.outdir, app.builder.imagedir, outfname)
    #inrelfn = posixpath.join(relative_uri(app.builder.env.docname, app.builder.imagedir), infname)

    if path.isfile(outfullfn):
        return outrelfn, outfullfn

    ensuredir(path.dirname(outfullfn))

    ditaa_args = [app.builder.config.ditaa]
    ditaa_args.extend(app.builder.config.ditaa_args)
    ditaa_args.extend(options)
    ditaa_args.extend( [infname, outfname] ) # use relative path
    f = open(infullfn, 'wb')
    f.write(code)
    f.close()
    currpath = os.getcwd()
    os.chdir(path.join(app.builder.outdir, app.builder.imagedir))

    try:
        if app.builder.config.ditaa_log_enable:
            print("rending %s" %(outfullfn))
        #app.builder.warn(ditaa_args)
        p = Popen(ditaa_args, stdout=PIPE, stdin=PIPE, stderr=PIPE)
    except OSError as err:
        if err.errno != ENOENT:   # No such file or directory
            raise
        app.builder.warn('ditaa command %r cannot be run (needed for ditaa '
                          'output), check the ditaa setting' %
                          app.builder.config.ditaa)
        app.builder._ditaa_warned_dot = True
        os.chdir(currpath)
        return None, None

    os.chdir(currpath)
    wentWrong = False
    try:
        # Ditaa may close standard input when an error occurs,
        # resulting in a broken pipe on communicate()
        stdout, stderr = p.communicate(code)
    except OSError as err:
        if err.errno != EPIPE:
            raise
        wentWrong = True
    except IOError as err:
        if err.errno != EINVAL:
            raise
        wentWrong = True
    if wentWrong:
        # in this case, read the standard output and standard error streams
        # directly, to get the error message(s)
        stdout, stderr = p.stdout.read(), p.stderr.read()
        p.wait()
    if p.returncode != 0:
        raise DitaaError('ditaa exited with error:\n[stderr]\n%s\n'
                            '[stdout]\n%s' % (stderr, stdout))
    return outrelfn, outfullfn

def on_doctree_resolved(app, doctree):
    #print "app.builder.env.docname: ", app.builder.env.docname
    for node in doctree.traverse(ditaa):
        # Generate the output png files
        relfn, outfn = render_ditaa(app, node['code'], node['options'], app.builder.format, "ditaa")
        image = nodes.image(uri=relfn, candidates={'*': outfn}, **node['img_options'])
        #for (k, v) in options.items():
        #    image[k] = v
        node.parent.replace(node, image)

def setup(app):
    app.add_node(ditaa, html=(None, None),
                 #latex=(latex_visit_ditaa, None),
                 )
    app.add_directive('ditaa', Ditaa)

    try:
        ditaa_cmd = os.environ['SPHINX_DITAA_CMD']
    except:
        ditaa_cmd = 'ditaa'

    try:
        ditaa_arg = os.environ['SPHINX_DITAA_ARG'].split(':')
    except:
        ditaa_arg = []

    app.add_config_value('ditaa', ditaa_cmd , 'html')
    app.add_config_value('ditaa_args', ditaa_arg, 'html')
    app.add_config_value('ditaa_log_enable', True, 'html')
    app.connect('doctree-read', on_doctree_resolved)
