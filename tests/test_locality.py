import httpx
from test_tavily import source, spec_fixture

from surreal_estate.channels.apis.common import Location
from surreal_estate.channels.web.locality import anchored_queries, local_spec, relevant_source
from surreal_estate.orchestrator.context import RunContext


def test_queries_preserve_street_and_confirmed_neighborhood():
    _, spec = spec_fixture()
    spec = spec.model_copy(update={'address_anchor': '121 S Highland Ave, Pittsburgh, PA 15206',
                                   'neighborhood': 'East Liberty'})
    queries = anchored_queries(spec, ['Pittsburgh local news'])
    assert all('East Liberty' in q for q in queries)
    assert 'Highland Ave' in queries[1]
    assert '121' not in queries[0]
    assert relevant_source(source('East Liberty residents discuss street construction.'), spec)
    assert not relevant_source(source('Fairywood residents discuss their neighborhood history.'), spec)


async def test_official_neighborhood_lookup_is_shared_across_topics():
    _, spec = spec_fixture()
    requests = []
    def handle(request):
        requests.append(request)
        assert request.url.params['outFields'] == 'hood'
        return httpx.Response(200, json={'features': [{'attributes': {'hood': 'East Liberty'}}]})
    ctx = RunContext(geocoded_location=Location(40.4608, -79.9249, '121 S Highland Ave'))
    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as http:
        search = type('Search', (), {'http': http})()
        first = await local_spec(spec, search, ctx)
        second = await local_spec(spec, search, ctx)
    assert first.neighborhood == second.neighborhood == 'East Liberty'
    assert len(requests) == 1


def test_partial_hours_do_not_support_daily_service_or_permanent_closure():
    from surreal_estate.llm.claim_checks import unsupported_hours_claim
    assert unsupported_hours_claim('The restaurant offers daily service from 11 to 8.', 'Open now 11AM - 8PM')
    assert unsupported_hours_claim('The restaurant is permanently closed.', 'Closing Soon; 132 S Highland Ave')
    assert not unsupported_hours_claim('The restaurant is open daily.', 'Open Monday through Sunday')
    assert not unsupported_hours_claim('Residents discuss daily life.', 'People enjoy the neighborhood')


async def test_planner_neighborhood_guess_is_not_used_without_boundary_support():
    _, spec = spec_fixture()
    spec = spec.model_copy(update={'neighborhood': 'Invented neighborhood'})
    result = await local_spec(spec, object(), RunContext())
    assert result.neighborhood is None
    assert 'GRANT' in anchored_queries(result, [])[0].upper()
