// Season 3 native targets; legacy profiles and replays keep their raw values.
appFilters.filter('characteristic', function() {
  return function(player, name) {
    if (!player || player[name] === null || player[name] === undefined) return '–';
    var value = player[name];
    return player.target_characteristics && ['ag', 'pa', 'av'].indexOf(name) !== -1 ? value + '+' : value;
  };
});

appFilters.filter('hasPassingAbility', function() {
  return function(team) {
    return !!team && Object.keys(team.players_by_id).some(function(id) {
      return team.players_by_id[id].target_characteristics;
    });
  };
});

appFilters.filter('range', function() {
  return function(input, total) {
    total = parseInt(total);
    for (var i=0; i<total; i++)
      input.push(i);
    return input;
  };
});

appFilters.filter('board', function() {
  return function(input) {
    total = parseInt(total);
    for (var i=0; i<total; i++)
      input.push(i);
    return input;
  };
});

app.filter('reverse', function() {
  return function(items) {
    return items.slice().reverse();
  };
});
