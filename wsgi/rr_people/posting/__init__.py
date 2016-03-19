from wsgi.rr_people.posting.copy_gen import COPY, CopyPostGenerator
from wsgi.rr_people.posting.imgur_gen import ImgurPostsProvider, IMGUR

POST_GENERATOR_OBJECTS = {IMGUR: ImgurPostsProvider, COPY: CopyPostGenerator}


