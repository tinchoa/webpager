import lxml
from lxml.html import tostring
from lxml.html.clean import Cleaner

from urlparse import urlparse, parse_qs
import numpy as np

from sklearn.base import BaseEstimator, TransformerMixin
from sklearn.feature_extraction import DictVectorizer
from sklearn.feature_extraction.text import CountVectorizer

from .functions import parent_tag, block_length, number_pattern, url_edit_distance
from .preprocess import Tagset


_cleaner = Cleaner(
    style=True,
    scripts=True,
    embedded=True,
    links=True,
    page_structure=False,
    remove_unknown_tags=False,
    meta=False,
    safe_attrs_only=False
)

def tokenize(text):
    return text.split()

def get_text(anchor):
    return anchor.text

def get_attr_text(anchor):
    return anchor.get('class', '') + anchor.get('id', '')

def get_query_params(anchor):
    url = anchor.get('href', '')
    return " ".join(parse_qs(urlparse(url).query).keys())

default_funcs = (parent_tag, block_length, number_pattern)

class HtmlFeaturesExtractor(BaseEstimator):
    """
    Extract the features for all the anchors from a HTML page.
    """
    def __init__(self, default_tags=('PAGE',), tokenize=tokenize):
        self.tagset = Tagset(default_tags)
        self.tokenize = tokenize

    @classmethod
    def clean_html(cls, html, encoding=None):
        parser = lxml.html.HTMLParser(encoding=encoding)

        if isinstance(html, unicode) and encoding is not None:
            html = html.encode(encoding)

        html = lxml.html.document_fromstring(html, parser=parser)
        return _cleaner.clean_html(html)

    def _parse_html(self, html, encoding=None):
        return self.clean_html(html, encoding)

    def fit_transform(self, X, y=None, encoding=None):
        """Convert the HTML data to list of the features.

        Parameters
        ----------
        X: a (HTML, url) tuple
        y is ignored.

        Returns
        -------
        A list of anchors and corresponding labels.

        """
        x, baseurl = X
        html = self.tagset.encode_tags(x)
        doc = self.clean_html(html, encoding)
        doc.make_links_absolute(baseurl)

        anchors = []
        labels = []
        for anchor in doc.iter('a'):
            tokens = self.tokenize(anchor.text or '')
            no_tag_tokens = [token for token in tokens if not \
                (self.tagset.start_tag_or_none(token) or self.tagset.end_tag_or_none(token))]
            anchor.text = u" " .join(no_tag_tokens)
            anchors.append(anchor)
            labels.append(1 if len(tokens) != len(no_tag_tokens) else 0)

        return anchors, labels

class AnchorContextTransformer(BaseEstimator, TransformerMixin):
    """
    Extract the context features for anchors.
    """
    def __init__(self, feature_funcs):
        self.feature_funcs = feature_funcs
        self.dict_vectorizer = DictVectorizer()

    def get_feature_names(self):
        return self.dict_vectorizer.get_feature_names()

    def fit_transform(self, X, y=None):
        return self.dict_vectorizer.fit_transform(self._apply_funcs(anchor, url) for anchor, url in X)

    def transform(self, X):
        return self.dict_vectorizer.transform(self._apply_funcs(anchor, url) for anchor, url in X)

    def _apply_funcs(self, anchor, url):
        d = {}
        for func in self.feature_funcs:
            d.update(func(anchor, url))
        return d

class AnchorTextTransformer(BaseEstimator, TransformerMixin):
    """
    Extract the text features for anchors.
    """
    def __init__(self, analyazer='char', ngram_range=(2, 4),
                 min_df=1, binary=True, get_text=get_text):
        self._get_text = get_text
        self._vectorizer = CountVectorizer(analyzer=analyazer, ngram_range=ngram_range, \
                                           min_df=min_df, binary=binary)

    def get_feature_names(self):
        return self._vectorizer.get_feature_names()

    def fit_transform(self, X, y=None):
        texts = [self._get_text(anchor) for anchor, _ in X]
        return self._vectorizer.fit_transform(texts)

    def transform(self, X):
        texts = [self._get_text(anchor) for anchor, _ in X]
        return self._vectorizer.transform(texts)

class AnchorEditDistanceTransformer(BaseEstimator, TransformerMixin):

    def get_feature_names(self):
        return np.array(['edit_distance'])

    def fit(self, X, y=None):
        return self

    def transform(self, X):
        distances = [url_edit_distance(anchor, url) for anchor, url in X]
        r = np.array(distances)
        r = np.reshape(r, (r.shape[0], 1))
        return r

AnchorTransformers = [('anchor_text', AnchorTextTransformer(get_text=get_text)),
                      ('anchor_class_id', AnchorTextTransformer(get_text=get_attr_text)),
                      ('anchor_query_params', AnchorTextTransformer(get_text=get_query_params)),
                      ('anchor_misc', AnchorContextTransformer(default_funcs)),
                      ('anchor_edit_distance', AnchorEditDistanceTransformer())]