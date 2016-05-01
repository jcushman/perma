import time

from perma.models import *

from .utils import PermaTestCase


class CaptureJobTestCase(PermaTestCase):

    fixtures = ['fixtures/users.json',
                'fixtures/folders.json',
                ]

    def setUp(self):
        super(CaptureJobTestCase, self).setUpClass()

        self.user_one = LinkUser.objects.get(pk=1)
        self.user_two = LinkUser.objects.get(pk=2)

    ### HELPERS ###

    def _create_capture_job(self, user, human=True):
        link = Link(created_by=user, submitted_url="http://example.com")
        link.save()
        capture_job = CaptureJob(link=link, human=human)
        capture_job.save()
        return capture_job

    def assertNextJobsMatch(self, expected_next_jobs):
        next_jobs = []
        for _ in expected_next_jobs:
            next_jobs.append(CaptureJob.get_next_job(reserve=True))
            time.sleep(1)  # sleep so capture_start_time ends up with different seconds for consistent ordering
        self.assertListEqual(next_jobs, expected_next_jobs)

    ### TESTS ###

    def test_one_job_per_user(self):
        """ Jobs should be processed round-robin, one per user. """
        jobs = [
            self._create_capture_job(self.user_one),
            self._create_capture_job(self.user_one),
            self._create_capture_job(self.user_one),
            self._create_capture_job(self.user_two),
            self._create_capture_job(self.user_one),
            self._create_capture_job(self.user_one),
            self._create_capture_job(self.user_one),
            self._create_capture_job(self.user_two),
        ]
        self.assertNextJobsMatch([jobs[0], jobs[3], jobs[1], jobs[7], jobs[2], jobs[4], jobs[5], jobs[6]])

    def test_humans_preferred(self):
        """ Jobs with human=True should be processed before jobs with human=False. """
        jobs = [
            self._create_capture_job(self.user_one, human=False),
            self._create_capture_job(self.user_two)
        ]
        self.assertNextJobsMatch([jobs[1], jobs[0]])
