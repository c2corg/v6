import datetime
from c2corg_api.caching import cache_document_version
from c2corg_api.models import DBSession
from c2corg_api.models.article import Article
from c2corg_api.models.image import Image
from c2corg_api.models.outing import Outing
from c2corg_api.models.report import ArchiveReport, Report, REPORT_TYPE, \
    ArchiveReportLocale, ReportLocale
from c2corg_api.models.association import AssociationLog, Association
from c2corg_api.models.cache_version import get_cache_key
from c2corg_api.models.document_history import DocumentVersion, HistoryMetaData
from c2corg_api.models.route import Route
from c2corg_api.models.user import User
from c2corg_api.models.waypoint import Waypoint
from c2corg_api.tests.search import reset_search_index

from c2corg_api.models.document import DocumentLocale, DocumentGeometry, \
    ArchiveDocument
from c2corg_api.views.document import DocumentRest

from c2corg_api.tests.views import BaseDocumentTestRest
from c2corg_common.attributes import quality_types
from dogpile.cache.api import NO_VALUE

from sqlalchemy.sql.expression import and_, over
from sqlalchemy.sql.functions import func


class TestReportRest(BaseDocumentTestRest):

    def setUp(self):  # noqa
        self.set_prefix_and_model(
            "/reports", REPORT_TYPE, Report, ArchiveReport,
            ArchiveReportLocale)
        BaseDocumentTestRest.setUp(self)
        self._add_test_data()

    def test_get_collection(self):
        body = self.get_collection()
        doc = body['documents'][0]
        self.assertIn('geometry', doc)

    def test_get_collection_paginated(self):
        self.app.get("/reports?offset=invalid", status=400)

        self.assertResultsEqual(
            self.get_collection({'offset': 0, 'limit': 0}), [], 4)

        self.assertResultsEqual(
            self.get_collection({'offset': 0, 'limit': 1}),
            [self.report4.document_id], 4)
        self.assertResultsEqual(
            self.get_collection({'offset': 0, 'limit': 2}),
            [self.report4.document_id, self.report3.document_id], 4)
        self.assertResultsEqual(
            self.get_collection({'offset': 1, 'limit': 2}),
            [self.report3.document_id, self.report2.document_id], 4)

    def test_get_collection_lang(self):
        self.get_collection_lang()

    def test_get_collection_search(self):
        reset_search_index(self.session)

        self.assertResultsEqual(
            self.get_collection_search({'l': 'en'}),
            [self.report4.document_id, self.report1.document_id], 2)

        self.assertResultsEqual(
            self.get_collection_search({'act': ['hiking']}),
            [self.report4.document_id, self.report3.document_id,
             self.report2.document_id, self.report1.document_id], 4)

    def test_get(self):
        body = self.get(self.report1, user='moderator')
        self.assertNotIn('report', body)
        self.assertIn('geometry', body)
        self.assertIsNone(body.get('geometry'))
        associations = body['associations']
        self.assertIn('images', associations)
        self.assertIn('articles', associations)
        self.assertIn('outings', associations)
        self.assertIn('routes', associations)

        linked_images = associations.get('images')
        self.assertEqual(len(linked_images), 0)
        linked_articles = associations.get('articles')
        self.assertEqual(len(linked_articles), 0)
        linked_outings = associations.get('outings')
        self.assertEqual(len(linked_outings), 1)
        linked_routes = associations.get('routes')
        self.assertEqual(len(linked_routes), 1)

        self.assertEqual(body.get('activities'), self.report1.activities)

        self.assertIn('nb_participants', body)
        self.assertIn('nb_impacted', body)
        self.assertIn('event_type', body)
        self.assertEqual(body.get('event_type'), ['stone_fall'])
        self.assertIn('date', body)
        self.assertEqual(body.get('date'), None)

        locale_en = self.get_locale('en', body.get('locales'))
        self.assertEqual(
          locale_en.get('place'), 'some place descrip. in english')
        locale_fr = self.get_locale('fr', body.get('locales'))
        self.assertEqual(
          locale_fr.get('place'), 'some place descrip. in french')

    def test_get_as_guest(self):
        body = self.get(self.report1, user=None)

        # common user should not see personal data in the report
        self.assertNotIn('author_status', body)
        self.assertNotIn('activity_rate', body)
        self.assertNotIn('nb_outings', body)
        self.assertNotIn('age', body)
        self.assertNotIn('gender', body)
        self.assertNotIn('previous_injuries', body)
        self.assertNotIn('autonomy', body)

    def test_get_as_contributor_not_author(self):
        body = self.get(self.report4, user='contributor')

        # common user should not see personal data in the report
        self.assertNotIn('author_status', body)
        self.assertNotIn('activity_rate', body)
        self.assertNotIn('nb_outings', body)
        self.assertNotIn('age', body)
        self.assertNotIn('gender', body)
        self.assertNotIn('previous_injuries', body)
        self.assertNotIn('autonomy', body)

    def test_get_as_moderator(self):
        body = self.get(self.report1, user='moderator')

        # MODERATOR CAN SEE PERSONAL DATA IN THE REPORT
        self.assertIn('author_status', body)
        self.assertIn('activity_rate', body)
        self.assertIn('nb_outings', body)
        self.assertIn('age', body)
        self.assertIn('gender', body)
        self.assertIn('previous_injuries', body)
        self.assertIn('autonomy', body)

    def test_get_lang(self):
        self.get_lang(self.report1, user='contributor')

    def test_get_new_lang(self):
        self.get_new_lang(self.report1, user='moderator')

    def test_get_404(self):
        self.get_404(user='moderator')

    def test_get_version(self):
        self.get_version(self.report1, self.report1_version)

    def test_get_version_etag(self):
        url = '{0}/{1}/en/{2}'.format(
                self._prefix, str(self.report1.document_id),
                str(self.report1_version.id))
        response = self.app.get(url, status=200)

        # check that the ETag header is set
        headers = response.headers
        etag = headers.get('ETag')
        self.assertIsNotNone(etag)

        # then request the document again with the etag
        headers = {
            'If-None-Match': etag
        }
        self.app.get(url, status=304, headers=headers)

    def test_get_version_caching(self):
        url = '{0}/{1}/en/{2}'.format(
                self._prefix, str(self.report1.document_id),
                str(self.report1_version.id))
        cache_key = '{0}-{1}'.format(
            get_cache_key(self.report1.document_id, 'en'),
            self.report1_version.id)

        cache_value = cache_document_version.get(cache_key)
        self.assertEqual(cache_value, NO_VALUE)

        # check that the response is cached
        self.app.get(url, status=200)

        cache_value = cache_document_version.get(cache_key)
        self.assertNotEqual(cache_value, NO_VALUE)

        # check that values are returned from the cache
        fake_cache_value = {'document': 'fake doc'}
        cache_document_version.set(cache_key, fake_cache_value)

        response = self.app.get(url, status=200)
        body = response.json
        self.assertEqual(body, fake_cache_value)

    def test_get_info(self):
        body, locale = self.get_info(self.report1, 'en')
        self.assertEqual(locale.get('lang'), 'en')

    def test_get_info_best_lang(self):
        body, locale = self.get_info(self.report1, 'es')
        self.assertEqual(locale.get('lang'), 'fr')

    def test_get_info_404(self):
        self.get_info_404()

    def test_post_error(self):
        body = self.post_error({}, user='moderator')
        errors = body.get('errors')
        self.assertEqual(len(errors), 1)
        self.assertCorniceRequired(errors[0], 'activities')

    def test_post_missing_title(self):
        body_post = {
            'activities': ['hiking'],
            'event_type': ['stone_fall'],
            'nb_participants': 5,
            'locales': [
                {'lang': 'en'}
            ]
        }
        self.post_missing_title(body_post, user='moderator')

    def test_post_non_whitelisted_attribute(self):
        body = {
            'activities': ['hiking'],
            'event_type': ['stone_fall'],
            'nb_participants': 5,
            'protected': True,
            'locales': [
                {'lang': 'en', 'place': 'some place description',
                 'title': 'Lac d\'Annecy'}
            ]
        }
        self.post_non_whitelisted_attribute(body, user='moderator')

    def test_post_missing_content_type(self):
        self.post_missing_content_type({})

    def test_post_success(self):
        body = {
            'document_id': 123456,
            'version': 567890,
            'activities': ['hiking'],
            'event_type': ['stone_fall'],
            'nb_participants': 5,
            'associations': {
                'images': [
                    {'document_id': self.image2.document_id}
                ],
                'articles': [
                    {'document_id': self.article2.document_id}
                ]
            },
            'geometry': {
                'version': 1,
                'document_id': self.waypoint2.document_id,
                'geom':
                    '{"type": "Point", "coordinates": [635956, 5723604]}'
            },
            'locales': [
                {'title': 'Lac d\'Annecy', 'lang': 'en'}
            ]
        }
        body, doc = self.post_success(body, user='moderator',
                                      validate_with_auth=True)
        version = doc.versions[0]

        archive_report = version.document_archive
        self.assertEqual(archive_report.activities, ['hiking'])
        self.assertEqual(archive_report.event_type, ['stone_fall'])
        self.assertEqual(archive_report.nb_participants, 5)

        archive_locale = version.document_locales_archive
        self.assertEqual(archive_locale.lang, 'en')
        self.assertEqual(archive_locale.title, 'Lac d\'Annecy')

        # check if geometry is stored in database afterwards
        self.assertIsNotNone(doc.geometry)

        # check that a link to the associated waypoint is created
        association_img = self.session.query(Association).get(
            (doc.document_id, self.image2.document_id))
        self.assertIsNotNone(association_img)

        association_img_log = self.session.query(AssociationLog). \
            filter(AssociationLog.parent_document_id ==
                   doc.document_id). \
            filter(AssociationLog.child_document_id ==
                   self.image2.document_id). \
            first()
        self.assertIsNotNone(association_img_log)

        # check that a link to the associated report is created
        association_art = self.session.query(Association).get(
            (doc.document_id, self.article2.document_id))
        self.assertIsNotNone(association_art)

        association_art_log = self.session.query(AssociationLog). \
            filter(AssociationLog.parent_document_id ==
                   doc.document_id). \
            filter(AssociationLog.child_document_id ==
                   self.article2.document_id). \
            first()
        self.assertIsNotNone(association_art_log)

    def test_post_as_contributor_and_get_as_author(self):
        body_post = {
            'document_id': 111,
            'version': 1,
            'activities': ['hiking'],
            'event_type': ['stone_fall'],
            'nb_participants': 666,
            'nb_impacted': 666,
            'locales': [
                # {'title': 'Lac d\'Annecy', 'lang': 'fr'},
                {'title': 'Lac d\'Annecy', 'lang': 'en'}
            ]
        }

        # create document (POST uses GET schema inside validation)
        body_post, doc = self.post_success(body_post, user='contributor')
        # version = doc.versions[0]

        report_id = doc.document_id
        user_id = 2  # ID from postgres of the user 'contributor'

        t = DBSession.query(
            ArchiveDocument.document_id.label('document_id'),
            User.id.label('user_id'),
            User.name.label('name'),
            over(
                func.rank(), partition_by=ArchiveDocument.document_id,
                order_by=HistoryMetaData.id).label('rank')). \
            select_from(ArchiveDocument). \
            join(
            DocumentVersion,
            and_(
                ArchiveDocument.document_id == DocumentVersion.document_id,
                ArchiveDocument.version == 1)). \
            join(HistoryMetaData,
                 DocumentVersion.history_metadata_id == HistoryMetaData.id). \
            join(User,
                 HistoryMetaData.user_id == User.id). \
            filter(ArchiveDocument.document_id == report_id,
                   HistoryMetaData.user_id == user_id). \
            subquery('t')

        query = DBSession.query(
            t.c.document_id, t.c.user_id, t.c.name). \
            filter(t.c.rank == 1)

        author_for_documents = {
            document_id: {
                'name': name,
                'user_id': user_id
            } for document_id, user_id, name in query
            }

        document_found = False

        for document in author_for_documents:
            if document == report_id:
                document_found = True

        # the contributor is successfully set as author in DB
        self.assertEqual(document_found, True)

        # AUTHORIZED CONTRIBUTOR CAN SEE PERSONAL DATA IN THE REPORT
        body = self.get(doc, user='contributor', ignore_checks=True)
        self.assertNotIn('report', body)

        self.assertIn('author_status', body)
        self.assertIn('activity_rate', body)
        self.assertIn('nb_outings', body)
        self.assertIn('age', body)
        self.assertIn('gender', body)
        self.assertIn('previous_injuries', body)
        self.assertIn('autonomy', body)

    def test_put_wrong_document_id(self):
        body = {
            'document': {
                'document_id': '9999999',
                'version': self.report1.version,
                'activities': ['hiking'],
                'event_type': ['avalanche'],
                'nb_participants': 5,
                'locales': [
                    {'lang': 'en', 'title': 'Lac d\'Annecy',
                     'version': self.locale_en.version}
                ]
            }
        }
        self.put_wrong_document_id(body, user='moderator')

    def test_put_wrong_document_version(self):
        body = {
            'document': {
                'document_id': self.report1.document_id,
                'version': -9999,
                'activities': ['hiking'],
                'event_type': ['avalanche'],
                'nb_participants': 5,
                'locales': [
                    {'lang': 'en', 'title': 'Lac d\'Annecy',
                     'version': self.locale_en.version}
                ]
            }
        }
        self.put_wrong_version(
            body, self.report1.document_id, user='moderator')

    def test_put_wrong_locale_version(self):
        body = {
            'document': {
                'document_id': self.report1.document_id,
                'version': self.report1.version,
                'activities': ['hiking'],
                'event_type': ['avalanche'],
                'nb_participants': 5,
                'locales': [
                    {'lang': 'en', 'title': 'Lac d\'Annecy',
                     'version': -9999}
                ]
            }
        }
        self.put_wrong_version(
            body, self.report1.document_id, user='moderator')

    def test_put_wrong_ids(self):
        body = {
            'document': {
                'document_id': self.report1.document_id,
                'version': self.report1.version,
                'activities': ['hiking'],
                'event_type': ['avalanche'],
                'nb_participants': 5,
                'locales': [
                    {'lang': 'en', 'title': 'Lac d\'Annecy',
                     'version': self.locale_en.version}
                ]
            }
        }
        self.put_wrong_ids(body, self.report1.document_id, user='moderator')

    def test_put_no_document(self):
        self.put_put_no_document(self.report1.document_id, user='moderator')

    def test_put_success_all(self):
        body = {
            'message': 'Update',
            'document': {
                'document_id': self.report1.document_id,
                'version': self.report1.version,
                'quality': quality_types[1],
                'activities': ['hiking'],
                'event_type': ['stone_fall'],
                'nb_participants': 333,
                'nb_impacted': 666,
                'age': 50,
                'rescue': False,
                'associations': {
                    'images': [
                        {'document_id': self.image2.document_id}
                    ],
                    'articles': [
                        {'document_id': self.article2.document_id}
                    ]
                },
                'geometry': {
                    'geom':
                        '{"type": "Point", "coordinates": [635956, 5723604]}'
                },
                'locales': [
                    {'lang': 'en', 'title': 'New title',
                     'place': 'some NEW place descrip. in english',
                     'version': self.locale_en.version}
                ]
            }
        }
        (body, report1) = self.put_success_all(
            body, self.report1, user='moderator', cache_version=3)

        self.assertEquals(report1.activities, ['hiking'])
        locale_en = report1.get_locale('en')
        self.assertEquals(locale_en.title, 'New title')

        # version with lang 'en'
        versions = report1.versions
        version_en = self.get_latest_version('en', versions)
        archive_locale = version_en.document_locales_archive
        self.assertEqual(archive_locale.title, 'New title')
        self.assertEqual(archive_locale.place,
                         'some NEW place descrip. in english')

        archive_document_en = version_en.document_archive
        self.assertEqual(archive_document_en.activities, ['hiking'])
        self.assertEqual(archive_document_en.event_type, ['stone_fall'])
        self.assertEqual(archive_document_en.nb_participants, 333)
        self.assertEqual(archive_document_en.nb_impacted, 666)

        # version with lang 'fr'
        version_fr = self.get_latest_version('fr', versions)
        archive_locale = version_fr.document_locales_archive
        self.assertEqual(archive_locale.title, 'Lac d\'Annecy')

        # check if geometry is stored in database afterwards
        self.assertIsNotNone(report1.geometry)
        # check that a link to the associated image is created
        association_img = self.session.query(Association).get(
            (report1.document_id, self.image2.document_id))
        self.assertIsNotNone(association_img)

        association_img_log = self.session.query(AssociationLog). \
            filter(AssociationLog.parent_document_id ==
                   report1.document_id). \
            filter(AssociationLog.child_document_id ==
                   self.image2.document_id). \
            first()
        self.assertIsNotNone(association_img_log)

        # check that a link to the associated article is created
        association_main_art = self.session.query(Association).get(
            (report1.document_id, self.article2.document_id))
        self.assertIsNotNone(association_main_art)

        association_art_log = self.session.query(AssociationLog). \
            filter(AssociationLog.parent_document_id ==
                   report1.document_id). \
            filter(AssociationLog.child_document_id ==
                   self.article2.document_id). \
            first()
        self.assertIsNotNone(association_art_log)

    def test_put_success_figures_only(self):
        body = {
            'message': 'Changing figures',
            'document': {
                'document_id': self.report1.document_id,
                'version': self.report1.version,
                'quality': quality_types[1],
                'activities': ['hiking'],
                'event_type': ['stone_fall'],
                'nb_participants': 333,
                'nb_impacted': 666,
                'age': 50,
                'rescue': False,
                'locales': [
                    {'lang': 'en', 'title': 'Lac d\'Annecy',
                     'place': 'some place descrip. in english',
                     'version': self.locale_en.version}
                ]
            }
        }
        (body, report1) = self.put_success_figures_only(
            body, self.report1, user='moderator')

        self.assertEquals(report1.activities, ['hiking'])

    def test_put_success_lang_only(self):
        body = {
            'message': 'Changing lang',
            'document': {
                'document_id': self.report1.document_id,
                'version': self.report1.version,
                'quality': quality_types[1],
                'activities': ['hiking'],
                'event_type': ['stone_fall'],
                'locales': [
                    {'lang': 'en', 'title': 'New title',
                     'version': self.locale_en.version}
                ]
            }
        }
        (body, report1) = self.put_success_lang_only(
            body, self.report1, user='moderator')

        self.assertEquals(report1.get_locale('en').title, 'New title')

    def test_put_success_new_lang(self):
        """Test updating a document by adding a new locale.
        """
        body = {
            'message': 'Adding lang',
            'document': {
                'document_id': self.report1.document_id,
                'version': self.report1.version,
                'quality': quality_types[1],
                'activities': ['hiking'],
                'event_type': ['stone_fall'],
                'locales': [
                    {'lang': 'es', 'title': 'Lac d\'Annecy'}
                ]
            }
        }
        (body, report1) = self.put_success_new_lang(
            body, self.report1, user='moderator')

        self.assertEquals(report1.get_locale('es').title, 'Lac d\'Annecy')

    def test_put_as_author(self):
        body = {
            'message': 'Update',
            'document': {
                'document_id': self.report1.document_id,
                'version': self.report1.version,
                'quality': quality_types[1],
                'activities': ['paragliding'],  # changed
                'event_type': ['person_fall'],  # changed
                'age': 90,  # PERSONAL DATA CHANGED
                'locales': [
                    {'lang': 'en', 'title': 'Another final EN title',
                     'version': self.locale_en.version}
                ]
            }
        }

        (body, report1) = self.put_success_all(
            body, self.report1, user='contributor', cache_version=2)

        # version with lang 'en'
        versions = report1.versions
        version_en = self.get_latest_version('en', versions)
        archive_locale = version_en.document_locales_archive
        self.assertEqual(archive_locale.title, 'Another final EN title')

        archive_document_en = version_en.document_archive
        self.assertEqual(archive_document_en.activities, ['paragliding'])
        self.assertEqual(archive_document_en.event_type, ['person_fall'])
        self.assertEqual(archive_document_en.age, 90)

    # TODO - TRY TO REWRITE REPORT WRITTEN BY SOMEONE ELSE
    # def test_put_as_non_author(self):
    #     body = {
    #         'message': 'Update',
    #         'document': {
    #             'document_id': self.report4.document_id,
    #             'version': self.report4.version,
    #             'quality': quality_types[1],
    #             'activities': ['paragliding'],  # changed
    #             'event_type': ['person_fall'],  # changed
    #             'age': 90,  # PERSONAL DATA CHANGED
    #             'locales': [
    #                 {'lang': 'en', 'title': 'Another final EN title',
    #                  'version': self.locale_en.version}
    #             ]
    #         }
    #     }
    #
    #     (body, report4) = self.put_wrong_authorization(
    #         body, self.report4.document_id, user='contributor2')

    def _add_test_data(self):
        self.report1 = Report(activities=['hiking'],
                              event_type=['stone_fall'])
        self.locale_en = ReportLocale(lang='en',
                                      title='Lac d\'Annecy',
                                      place='some place descrip. in english')
        self.locale_fr = ReportLocale(lang='fr', title='Lac d\'Annecy',
                                      place='some place descrip. in french')

        self.report1.locales.append(self.locale_en)
        self.report1.locales.append(self.locale_fr)

        self.session.add(self.report1)
        self.session.flush()

        user_id = self.global_userids['contributor']
        DocumentRest.create_new_version(self.report1, user_id)
        self.report1_version = self.session.query(DocumentVersion). \
            filter(DocumentVersion.document_id ==
                   self.report1.document_id). \
            filter(DocumentVersion.lang == 'en').first()

        self.report2 = Report(activities=['hiking'],
                              event_type=['avalanche'],
                              nb_participants=5)
        self.session.add(self.report2)
        self.report3 = Report(activities=['hiking'],
                              event_type=['avalanche'],
                              nb_participants=5)
        self.session.add(self.report3)
        self.report4 = Report(activities=['hiking'],
                              event_type=['avalanche'],
                              nb_participants=5,
                              nb_impacted=5,
                              age=50)
        self.report4.locales.append(DocumentLocale(
            lang='en', title='Lac d\'Annecy'))
        self.report4.locales.append(DocumentLocale(
            lang='fr', title='Lac d\'Annecy'))
        self.session.add(self.report4)

        self.article2 = Article(
            categories=['site_info'], activities=['hiking'],
            article_type='collab')
        self.session.add(self.article2)
        self.session.flush()

        self.image2 = Image(
            filename='image2.jpg',
            activities=['paragliding'], height=1500)
        self.session.add(self.image2)
        self.session.flush()

        self.waypoint1 = Waypoint(
            waypoint_type='summit', elevation=2203)
        self.session.add(self.waypoint1)
        self.waypoint2 = Waypoint(
            waypoint_type='climbing_outdoor', elevation=2,
            rock_types=[],
            geometry=DocumentGeometry(
                geom='SRID=3857;POINT(635956 5723604)')
            )
        self.session.add(self.waypoint2)
        self.session.flush()

        self.outing3 = Outing(
            activities=['skitouring'], date_start=datetime.date(2016, 2, 1),
            date_end=datetime.date(2016, 2, 2)
        )
        self.session.add(self.outing3)
        self.route3 = Route(
            activities=['skitouring'], elevation_max=1500, elevation_min=700,
            height_diff_up=500, height_diff_down=500, durations='1')
        self.session.add(self.route3)
        self.session.flush()

        self.session.add(Association.create(
            parent_document=self.outing3,
            child_document=self.report1))
        self.session.add(Association.create(
            parent_document=self.route3,
            child_document=self.report1))
        self.session.flush()