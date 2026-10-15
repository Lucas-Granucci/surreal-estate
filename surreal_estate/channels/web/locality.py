"""Resolve search context from a public neighborhood boundary, never model memory."""
import re

from surreal_estate.channels.apis.common import public_json
from surreal_estate.models import ResearchQuerySpec
from surreal_estate.orchestrator.context import BudgetExceeded

NEIGHBORHOODS = 'https://pghbridgis.pittsburghpa.gov/federated/rest/services/Neighborhoods/MapServer/0/query'


async def local_spec(spec, search, ctx):
    # A planner-provided neighborhood is a guess until a boundary lookup supports it.
    spec = spec.model_copy(update={'neighborhood': None, 'neighborhood_source': None})
    if 'pittsburgh' not in spec.geography.lower() or not hasattr(search, 'http'):
        return spec
    if not ctx.research_area.get('attempted'):
        ctx.research_area['attempted'] = True
        location = ctx.geocoded_location
        point = ({'x': location.longitude, 'y': location.latitude} if location else
                 ctx.confirmed_geocode[0].get('coordinates') if ctx.confirmed_geocode else None)
        if point:
            import httpx
            try:
                data, uri = await public_json(search.http, ctx, 'pittsburgh_neighborhoods', NEIGHBORHOODS,
                    params={'f': 'json', 'geometry': f"{point['x']},{point['y']}",
                            'geometryType': 'esriGeometryPoint', 'inSR': 4326,
                            'spatialRel': 'esriSpatialRelIntersects', 'outFields': 'hood',
                            'returnGeometry': 'false', 'resultRecordCount': 5}, request_seconds=25,
                    retries=0)
                names = {f['attributes']['hood'] for f in data.get('features', [])
                         if isinstance(f.get('attributes', {}).get('hood'), str)}
                if len(names) == 1:
                    name = names.pop().strip()
                    if name and len(name) <= 120:
                        ctx.research_area.update(neighborhood=name, neighborhood_source=uri)
            except (httpx.HTTPError, ValueError, KeyError, TypeError, TimeoutError, BudgetExceeded):
                ctx.trace.append('web:neighborhood_lookup_unavailable:using_street')
    return ResearchQuerySpec.model_validate({**spec.model_dump(),
        **{k: v for k, v in ctx.research_area.items() if k != 'attempted'}})


def street_name(spec):
    street = (spec.address_anchor or '').split(',')[0]
    return re.sub(r'^\d+[A-Za-z]?\s+', '', street).strip()


def anchored_queries(spec, queries):
    street = street_name(spec)
    area = spec.neighborhood or street or spec.geography
    if spec.topic == 'neighborhood_discussion':
        forum = 'site:reddit.com/r/pittsburgh' if 'pittsburgh' in spec.geography.lower() else 'site:reddit.com'
        # Preserve local context while avoiding an exact house-number constraint.
        local = ' '.join(dict.fromkeys([area, street]))
        return [f'{area} {spec.geography} living resident experiences {forum}',
                f'{local} {spec.geography} neighborhood news development local discussion']
    local = ' '.join(dict.fromkeys([area, street]))
    discovery = f'restaurants near {spec.address_anchor or area} {spec.neighborhood or ""} reviews menus'
    follow_up = queries[-1] if queries else 'restaurant customer reviews official menus'
    return [discovery.strip(), f'{local} {spec.geography} {follow_up}']


def relevant_source(source, spec):
    """Keep broad results as discovery only; never turn unrelated places into a brief."""
    text = (source.title + ' ' + str(source.details.get('content', ''))).casefold()
    anchors = [spec.neighborhood] if spec.neighborhood else []
    street = street_name(spec)
    # Accommodate abbreviated/full street types without using house numbers as identity.
    core = re.sub(r'\b(n|s|e|w|north|south|east|west|st|street|ave|avenue|blvd|boulevard|rd|road)\b',
                  '', street, flags=re.IGNORECASE).strip()
    if core:
        anchors.append(core)
    return not anchors or any(anchor.casefold() in text for anchor in anchors)
