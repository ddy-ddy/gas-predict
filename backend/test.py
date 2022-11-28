# -*- coding: utf-8 -*-
# @Time    : 2022/7/29 15:38
# @Author  : ddy
# @FileName: test.py
# @github  : https://github.com/ddy-ddy

import spacy

# Load English tokenizer, tagger, parser and NER
nlp = spacy.load("en_core_web_sm")

print(nlp("we're family"))

print(nlp(u"we're family"))