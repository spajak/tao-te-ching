import sys, re
from pathlib import Path
from zipfile import ZipFile
from bs4 import BeautifulSoup
import pystache as mustache

def main():
    id_ = '01 - Stephen Mitchell.xhtml'
    for f in Package.text_files:
        if f.name == id_:
            tr = Translation(f)
            build(tr)

class Package:
    ROOT = Path(__file__).parent
    text_dir = ROOT / "src" / "text"
    tmpl_dir = ROOT / "src" / "epub"
    dist_dir = ROOT / "dist"
    text_files = text_dir.glob('*.xhtml')
    tmpl_files = (tmpl_dir / 'Content').glob('*.*')

class EpubPackage:
    """Represents epub package and its structure"""
    pass

class EpubFile:
    """Represents a single file that is a part of epub package"""
    pass

class FileTemplate(EpubFile):
    """Represents a single file template that is a part of epub package"""
    def __init__(self, template, translation):
        self.template = template
        self.translation = translation
    def get_document(self):
        pass

def build(translation):
    Package.dist_dir.mkdir(exist_ok=True)
    def write(fname, content):
        output = Package.dist_dir / fname
        with open(output, 'w', encoding='utf-8') as of:
            of.write(content)
    variables = translation.meta()
    section_template = None
    for path in Package.tmpl_files:
        with open(path, 'r', encoding='utf-8') as f:
            template = f.read()
            if path.name == 'section.xhtml':
                section_template = template
                continue
            rendered = mustache.render(template, variables)
            write(path.name, rendered)
    if section_template:
        for section in translation.sections():
            variables['section_body'] = section.xhtml
            variables['section_label'] = section.label
            rendered = mustache.render(section_template, variables)
            write(section.id + '.xhtml', rendered)

class Translation:
    """Represents a translation document"""
    class Section:
        SECTIONS = {
            'dedication': None,
            'foreword': 'Foreword',
            'preface': 'Preface',
            'introduction': 'Introduction',
            'epigraph': None,
            'prologue': 'Prologue',
            'chapter': None,
            'epilogue': 'Epilogue',
            'afterword': 'Afterword',
            'footnotes': 'Notes',
            'endnotes': 'Notes',
            'appendix': 'Appendix',
            'acknowledgments': 'Acknowledgments'
        }
        def __init__(self, el, title_tag=None):
            self.el = el
            self.title_tag = title_tag
            self.type = el.get('epub:type')
            self.id = el.get('id') or self.type
            self.chapter = None
            self.title = None
            self.parse()
        @property
        def xhtml(self):
            return str(self.el)
        @property
        def label(self):
            return self.title if self.title else self.id.title()
        @property
        def order(self):
            idx = list(self.SECTIONS.keys()).index(self.type)
            idx = str(idx).rjust(len(self.SECTIONS), '0')
            if self.chapter:
                idx += self.id
            return idx
        def parse(self):
            if self.type is None:
                raise Exception('Section type is not set')
            if self.type == 'chapter':
                if not self.id:
                    raise Exception('Chapter must have an id')
                m = re.match(r'^ch-(\d+)$', self.id)
                if not m:
                    raise Exception(f'Chapter id value "{self.id}" is not valid')
                self.chapter = int(m[1])
                self.title = str(self.chapter)
            else:
                if self.type not in self.SECTIONS:
                    raise Exception(f'Section type "{self.type}" is not valid')
                self.title = self.SECTIONS[self.type]
                if self.title is not None:
                    if self.id != self.type:
                        self.title = self.id.title()
            self.make_title()
        def make_title(self):
            if self.title_tag and self.title:
                if self.el.h1 or self.el.h2:
                    return
                self.title_tag.string = self.title
                self.el.insert(0, self.title_tag)

    def __init__(self, path):
        self.path = path
        self.soup = None
        self.meta_ = {}
        self.sections_ = []
    def meta(self, key=None):
        self.load()
        return self.meta_[key] if key else self.meta_
    def sections(self):
        self.load()
        return self.sections_
    def load(self):
        if self.soup is not None:
            return
        with open(self.path, 'r', encoding='utf-8') as fp:
            self.soup = BeautifulSoup(fp, 'lxml')
            head = self.soup.head
            self.meta_['language'] = self.soup.html.get('lang')
            self.meta_['title'] = head.title.string
            self.meta_['toc_title'] = 'Table of contents'
            self.meta_['cover_label'] = 'Cover'
            for meta in head.find_all('meta'):
                if name := meta.get('name'):
                    self.meta_[name] = meta.get('content')
            sections_ = []
            for section in self.soup.body('section'):
                self.sections_.append(
                    Translation.Section(section, self.soup.new_tag('h2'))
                )
            self.sections_.sort(key=lambda x: x.order)
            items = []
            for item in self.sections_:
                items.append({
                    'label': item.label,
                    'path': item.id + '.xhtml',
                    'id': item.id
                })
            self.meta_['items'] = items

if __name__ == '__main__':
    main()
