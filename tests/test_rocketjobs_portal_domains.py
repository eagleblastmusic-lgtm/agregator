from agregator.sources.rocketjobs import (
    extract_employer_profile_url,
    extract_employer_website,
)


def test_employer_profile_must_stay_on_rocketjobs_host() -> None:
    html = '''
    <html><body>
      <a href="https://justjoin.it/brands/story/acme">ACME</a>
      <a href="https://justjoin.it/brands/story/acme">Zobacz profil firmy</a>
    </body></html>
    '''

    assert extract_employer_profile_url(
        html,
        "https://rocketjobs.pl/oferta-pracy/acme-test",
        "ACME",
    ) is None


def test_related_portal_domains_are_not_employer_websites() -> None:
    for website in (
        "https://justjoin.it/",
        "https://jobs.rocketjobs.com/",
    ):
        payload = (
            '{"socialMedia":['
            f'{{"link":"{website}","type":"Website"}}'
            "]}"
        )
        serialized = payload.replace('"', r'\"')
        html = f'''
        <html><body>
          <a href="{website}"></a>
          <script>self.__next_f.push([1,"{serialized}"])</script>
        </body></html>
        '''

        assert extract_employer_website(
            html,
            "https://rocketjobs.pl/brands/story/example",
        ) is None
