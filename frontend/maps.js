const Maps = (() => {
    const BASE_URL = "https://www.google.com/maps?q=";

    function buildMapUrl(query) {
        return `${BASE_URL}${encodeURIComponent(query)}&output=embed`;
    }

    function updateMap(frame, query) {
        if (!frame || !query) {
            return;
        }
        frame.src = buildMapUrl(query);
    }

    function updateForState(frame, state) {
        const safeState = state || "India";
        updateMap(frame, `polling booth in ${safeState}`);
    }

    function updateForLocation(frame, latitude, longitude) {
        updateMap(frame, `polling booth near ${latitude},${longitude}`);
    }

    return {
        updateForLocation,
        updateForState,
    };
})();
