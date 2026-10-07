
self.addEventListener('push', function(event) {
    if (event.data) {
        let data = event.data.json();
        let options = {
            body: data.body,
            icon: 'https://cdn-icons-png.flaticon.com/512/3665/3665939.png',
            badge: 'https://cdn-icons-png.flaticon.com/512/3665/3665939.png',
            data: data.data || {}
        };
        event.waitUntil(
            self.registration.showNotification(data.title, options)
        );
    }
});

self.addEventListener('notificationclick', function(event) {
    event.notification.close();
    let targetUrl = event.notification.data.url || '/';
    
    event.waitUntil(
        clients.matchAll({ type: 'window', includeUncontrolled: true }).then(function(clientList) {
            // Check if there's already a window open to this URL
            for (let i = 0; i < clientList.length; i++) {
                let client = clientList[i];
                if (client.url.includes(targetUrl) && 'focus' in client) {
                    return client.focus();
                }
            }
            if (clients.openWindow) {
                return clients.openWindow(targetUrl);
            }
        })
    );
});
