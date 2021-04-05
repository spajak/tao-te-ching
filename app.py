import sys, re, shutil
from datetime import datetime, timezone
from dataclasses import dataclass
from pathlib import Path
from zipfile import ZipFile
from bs4 import BeautifulSoup
import pystache as mustache

def main():
    id_ = '01 - Stephen Mitchell.xhtml'
    for f in Package.text_files:
        if f.name == id_:
            tr = Translations().load(f)
            build(tr)

class Package:
    ROOT = Path(__file__).parent
    text_dir = ROOT / "src" / "text"
    tmpl_dir = ROOT / "src" / "epub"
    dist_dir = ROOT / "dist"
    text_files = text_dir.glob('*.xhtml')
    tmpl_files = tmpl_dir.glob('*.*')

class EpubPackage:
    """Represents epub package and its structure"""
    pass

class EpubFile:
    """Represents a single file that is a part of epub package"""
    pass

container_xml = """
<?xml version="1.0" encoding="utf-8"?>
<container xmlns="urn:oasis:names:tc:opendocument:xmlns:container" version="1.0">
    <rootfiles>
        <rootfile full-path="Content/content.opf" media-type="application/oebps-package+xml"/>
    </rootfiles>
</container>
"""

container_files = (
    ('META-INF/container.xml', container_xml),
    ('mimetype', 'application/epub+zip')
)

def create_directory_structure(name):
    dir_ = Package.dist_dir / name
    if dir_.exists():
        shutil.rmtree(dir_)
    for fname, data in container_files:
        fpath = dir_ / fname
        if not fpath.parent.exists():
            fpath.parent.mkdir(parents=True)
        with open(fpath, 'w', encoding='utf-8') as fp:
            fp.write(data.strip() + "\n")
    dir_ = dir_ / 'Content'
    dir_.mkdir(parents=True, exist_ok=True)
    return dir_

def build(translation):
    dir_ = create_directory_structure(translation.name)
    def write(fname, content):
        output = dir_ / fname
        with open(output, 'w', encoding='utf-8') as of:
            of.write(content)
    section_template = None
    for path in Package.tmpl_files:
        with open(path, 'r', encoding='utf-8') as f:
            template = f.read()
            if path.name == 'section.xhtml':
                section_template = template
                continue
            rendered = mustache.render(template, translation)
            write(path.name, rendered)
    if section_template:
        for section in translation.sections:
            rendered = mustache.render(section_template, section)
            write(section.id + '.xhtml', rendered)

def date_modified():
    return datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')

def date():
    return datetime.now().strftime("%Y-%m-%d")

class Section:
    def __init__(self, type_, id_=None):
        self.type = type_
        self.id = id_ or self.type
        self.title = None
        self.language = "en"
        self.chapter = None
        self.body = None
    @property
    def label(self):
        return self.title if self.title else self.id.title()
    @property
    def html_title(self):
        return self.label

class Translation:
    """Represents a translation document"""
    def __init__(self, uuid):
        self.uuid = uuid
        self.language = "en"
        self.title = "Tao Te Ching"
        self.author = "Lao Tzu"
        self.translator = None
        self.year = None
        self.sections = []
        self.items = []
        self.toc_title = "Table of contents"
        self.cover_label = "Cover"
        self.source = "https://github.com/spajak/tao-te-ching"
        self.date_modified = date_modified()
        self.publisher = "Home"
        self.date = date()
        self.number_of_pages = 50
    @property
    def name(self):
        return "{} by {} - {}".format(
            self.title,
            self.author,
            self.translator
        )

class Translations:
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
    def __init__(self, insert_titles=True, insert_footnotes=False):
        self.insert_titles = insert_titles
        self.insert_footnotes = insert_footnotes
    @classmethod
    def section_sort_key(cls, section):
        idx = list(cls.SECTIONS.keys()).index(section.type)
        idx = str(idx).rjust(len(cls.SECTIONS), '0')
        return idx + section.id
    def insert_title(self, el, title, soup):
        if el.h1 or el.h2:
            return
        h2_tag = soup.new_tag('h2')
        h2_tag.string = title
        el.insert(0, h2_tag)
        el.insert(0, "\n")
    def extract_metadata(self, soup):
        metadata = {
            'language': soup.html.get('lang'),
            'title': soup.head.title.string
        }
        for meta in soup.head.find_all('meta'):
            if name := meta.get('name'):
                metadata[name] = meta.get('content')
        uuid = metadata['uuid']
        del metadata['uuid']
        return uuid, metadata
    def extract_chapter(self, id_):
        m = re.match(r'^ch-(\d+)$', id_)
        if not m:
            raise Exception(f'Chapter id value "{id_}" is not valid')
        return int(m[1])
    def extract_title(self, type_, id_):
        if type_ not in self.SECTIONS:
            raise Exception(f'Section type "{type_}" is not valid')
        title = self.SECTIONS[type_]
        if title is not None and id_ and id_ != type_:
            title = id_.title()
        return title
    def load(self, path):
        with open(path, 'r', encoding='utf-8') as fp:
            soup = BeautifulSoup(fp, 'lxml')
            uuid, metadata = self.extract_metadata(soup)
            record = Translation(uuid)
            for k, v in metadata.items():
                if hasattr(record, k):
                    setattr(record, k, v)
            sections = []
            for item in soup.body('section'):
                section = Section(item['epub:type'], item.get('id'))
                if lang := item.get('lang'):
                    section.language = lang
                else:
                    section.language = record.language
                if section.type == 'chapter':
                    section.chapter = self.extract_chapter(section.id)
                    section.title = str(section.chapter)
                else:
                    section.title = self.extract_title(section.type, section.id)
                if section.title and self.insert_titles:
                    self.insert_title(item, section.title, soup)
                section.body = str(item)
                sections.append(section)
            sections.sort(key=lambda s: Translations.section_sort_key(s))
            items = []
            for item in sections:
                items.append({
                    'id': item.id,
                    'label': item.label,
                    'path': item.id + '.xhtml'
                })
            record.sections = sections
            record.items = items
            return record

if __name__ == '__main__':
    main()
