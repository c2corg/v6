from c2corg_api.models.schema_utils import restrict_schema,\
    get_update_schema, get_create_schema
from c2corg_api.models.common.fields_image import fields_image
from sqlalchemy import (
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    SmallInteger,
    String
    )
from sqlalchemy.ext.declarative import declared_attr

from colander import MappingSchema, SchemaNode, Sequence
from colanderalchemy import SQLAlchemySchemaNode

from c2corg_api.models import schema, enums, Base, DBSession
from c2corg_api.models.utils import copy_attributes, ArrayOfEnum
from c2corg_api.models.document import (
    ArchiveDocument, Document, get_geometry_schema_overrides,
    schema_attributes, DocumentLocale,
    schema_locale_attributes)
from c2corg_api.models.common import document_types

IMAGE_TYPE = document_types.IMAGE_TYPE


class _ImageMixin(object):

    activities = Column(ArrayOfEnum(enums.activity_type))

    categories = Column(ArrayOfEnum(enums.image_category))

    image_type = Column(enums.image_type)

    author = Column(String(100))

    elevation = Column(SmallInteger)

    height = Column(SmallInteger)

    width = Column(SmallInteger)

    file_size = Column(Integer)

    @declared_attr
    def filename(self):
        return Column(String(30),
                      nullable=False,
                      unique=(self.__name__ == 'Image'))

    date_time = Column(DateTime(timezone=True))

    camera_name = Column(String(100))

    exposure_time = Column(Float)

    focal_length = Column(Float)

    fnumber = Column(Float)

    iso_speed = Column(SmallInteger)


attributes = [
    'activities', 'categories', 'image_type', 'author', 'elevation',
    'height', 'width', 'file_size', 'filename', 'camera_name', 'exposure_time',
    'focal_length', 'fnumber', 'iso_speed', 'date_time'
]


class Image(_ImageMixin, Document):
    """
    """
    __tablename__ = 'images'

    document_id = Column(
        Integer,
        ForeignKey(schema + '.documents.document_id'), primary_key=True)

    __mapper_args__ = {
        'polymorphic_identity': IMAGE_TYPE,
        'inherit_condition': Document.document_id == document_id
    }

    def to_archive(self):
        image = ArchiveImage()
        super(Image, self)._to_archive(image)
        copy_attributes(self, image, attributes)

        return image

    def update(self, other):
        super(Image, self).update(other)
        copy_attributes(other, self, attributes)


class ArchiveImage(_ImageMixin, ArchiveDocument):
    """
    """
    __tablename__ = 'images_archives'

    id = Column(
        Integer,
        ForeignKey(schema + '.documents_archives.id'), primary_key=True)

    __mapper_args__ = {
        'polymorphic_identity': IMAGE_TYPE,
        'inherit_condition': ArchiveDocument.id == id
    }

    __table_args__ = Base.__table_args__


# special schema for image locales: images can be created without title
schema_image_locale = SQLAlchemySchemaNode(
    DocumentLocale,
    # whitelisted attributes
    includes=schema_locale_attributes,
    overrides={
        'version': {
            'missing': None
        },
        'title': {
            'missing': ''
        }
    })

schema_image = SQLAlchemySchemaNode(
    Image,
    # whitelisted attributes
    includes=schema_attributes + attributes,
    overrides={
        'document_id': {
            'missing': None
        },
        'version': {
            'missing': None
        },
        'locales': {
            'children': [schema_image_locale]
        },
        'geometry': get_geometry_schema_overrides(['POINT'])
    })

schema_create_image = get_create_schema(schema_image)
schema_update_image = get_update_schema(schema_image)
schema_listing_image = restrict_schema(
    schema_image, fields_image.get('listing'))
schema_association_image = restrict_schema(schema_image, [
    'filename', 'locales.title', 'geometry.geom'
])


class SchemaImageList(MappingSchema):
    images = SchemaNode(
        Sequence(), schema_create_image, missing=None)


schema_create_image_list = SchemaImageList()


def is_personal(image_id):
    image_type = DBSession.query(Image.image_type). \
        select_from(Image.__table__). \
        filter(Image.document_id == image_id). \
        scalar()
    return image_type == 'personal'
