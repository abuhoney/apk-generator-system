/* Weather function — front-end logic */
(function () {
  'use strict';
  var form = document.getElementById('searchForm');
  var input = document.getElementById('cityInput');
  var card = document.getElementById('weatherCard');
  var errorCard = document.getElementById('errorCard');
  var recent = JSON.parse(localStorage.getItem('bardom_weather_recent') || '[]');

  var ICONS = {
    0:'☀️', 1:'🌤️', 2:'⛅', 3:'☁️', 45:'🌫️', 48:'🌫️',
    51:'🌦️', 53:'🌦️', 55:'🌧️', 56:'🌧️', 57:'🌧️',
    61:'🌧️', 63:'🌧️', 65:'⛈️', 66:'🌧️', 67:'⛈️',
    71:'🌨️', 73:'🌨️', 75:'❄️', 77:'❄️',
    80:'🌦️', 81:'🌧️', 82:'⛈️', 85:'🌨️', 86:'❄️',
    95:'⛈️', 96:'⛈️', 99:'⛈️'
  };

  function saveRecent(city) {
    recent = recent.filter(function (c) { return c !== city; });
    recent.unshift(city);
    recent = recent.slice(0, 10);
    localStorage.setItem('bardom_weather_recent', JSON.stringify(recent));
    renderRecent();
  }
  function renderRecent() {
    var ul = document.getElementById('recentList');
    ul.innerHTML = recent.map(function (c) { return '<li>' + c + '</li>'; }).join('');
    ul.querySelectorAll('li').forEach(function (li) {
      li.addEventListener('click', function () { input.value = li.textContent; search(); });
    });
  }

  function search() {
    var city = input.value.trim();
    if (!city) return;
    card.hidden = true; errorCard.hidden = true;
    fetch('https://geocoding-api.open-meteo.com/v1/search?name=' + encodeURIComponent(city) + '&count=1&language=en&format=json')
      .then(function (r) { return r.json(); })
      .then(function (geo) {
        if (!geo.results || !geo.results.length) throw new Error('City not found');
        var g = geo.results[0];
        return fetch('https://api.open-meteo.com/v1/forecast?latitude=' + g.latitude + '&longitude=' + g.longitude + '&current=temperature_2m,relative_humidity_2m,weather_code,wind_speed_10m&timezone=auto')
          .then(function (r) { return r.json(); })
          .then(function (wx) { return { geo: g, wx: wx }; });
      })
      .then(function (data) {
        var cur = data.wx.current;
        var code = cur.weather_code;
        document.getElementById('city').textContent = data.geo.name;
        document.getElementById('country').textContent = data.geo.country || '';
        document.getElementById('temp').textContent = Math.round(cur.temperature_2m) + '°C';
        document.getElementById('desc').textContent = WMO(code);
        document.getElementById('icon').textContent = ICONS[code] || '🌡️';
        document.getElementById('wind').textContent = cur.wind_speed_10m + ' km/h';
        document.getElementById('code').textContent = code;
        card.hidden = false;
        saveRecent(city);
      })
      .catch(function (e) {
        errorCard.textContent = 'Error: ' + e.message;
        errorCard.hidden = false;
      });
  }

  function WMO(code) {
    var map = {0:'Clear sky',1:'Mainly clear',2:'Partly cloudy',3:'Overcast',45:'Fog',48:'Rime fog',51:'Light drizzle',53:'Moderate drizzle',55:'Dense drizzle',61:'Slight rain',63:'Moderate rain',65:'Heavy rain',71:'Slight snow',73:'Moderate snow',75:'Heavy snow',80:'Rain showers',81:'Moderate showers',82:'Violent showers',95:'Thunderstorm',96:'Thunderstorm + hail',99:'Thunderstorm + heavy hail'};
    return map[code] || 'Unknown';
  }

  form.addEventListener('submit', function (e) { e.preventDefault(); search(); });
  renderRecent();
})();
