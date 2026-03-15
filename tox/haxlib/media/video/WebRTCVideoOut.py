
import json

class WebRTCVideoOut:
	"""
	Manages WebRTC peer connections from TouchDesigner to one or more browser tabs.
	Signaling (Offer/Answer/ICE) travels over the Oversite WebSocket channel.
	Each browser-side <webrtc-stream> component has a unique viewerId; the page's
	WebSocket sender ID (ws_sender) is used only for routing outgoing messages.
	"""
	def __init__(self, ownerComp):
		# The component to which this extension is attached
		self.ownerComp = ownerComp
		self.webrtcDAT: webrtcDAT = self.ownerComp.op('webrtc2')
		self.websocketsDAT: websocketDAT = self.ownerComp.op('websocket2')

		self.METADATA = {
			'apiVersion': '1.0.1', 'compVersion': '1.0.0',
			'compOrigin': '/webrtcDAT', 'projectName': "haxlib"
		}

		# WebRTC connections keyed by viewer_id (the webrtc-stream component's unique ID).
		self.connections = {}

		# conn_id → ws_sender: the WebSocket sender ID to route Offer/ICE back to.
		self.connection_ws_senders = {}

		# conn_id → viewer_id: included in Offer/ICE so the browser can match the right component.
		self.connection_viewer_ids = {}

		# clear out the connections
		self.Reset()

	def Reset(self):
		self.webrtcDAT.par.reset.pulse()
		self.websocketsDAT.par.reset.pulse()

	# WebSocket connection helpers

	def Connect(self, viewer_id, ws_sender):
		"""Close any existing connection for this viewer_id, open a new one and offer."""
		if viewer_id in self.connections:
			old_conn = self.connections[viewer_id]
			self.connection_ws_senders.pop(old_conn, None)
			self.connection_viewer_ids.pop(old_conn, None)
			try:
				self.webrtcDAT.closeConnection(old_conn)
			except:
				pass
		conn_id = self.webrtcDAT.openConnection()
		self.connections[viewer_id] = conn_id
		self.connection_ws_senders[conn_id] = ws_sender   # route replies to this WS client
		self.connection_viewer_ids[conn_id] = viewer_id   # echoed back so browser can filter

		# trackId must match the "WebRTC Video Track" parameter on VideoStreamOut TOP
		self.webrtcDAT.addTrack(conn_id, 'video_track_1', 'video')
		self.webrtcDAT.createOffer(conn_id)  # triggers OnOffer below


	def Disconnect(self, viewer_id):
		"""Close and remove the connection for this viewer_id."""
		if viewer_id in self.connections:
			conn_id = self.connections[viewer_id]
			self.connection_ws_senders.pop(conn_id, None)
			self.connection_viewer_ids.pop(conn_id, None)
			try:
				self.webrtcDAT.closeConnection(conn_id)
			except:
				pass
			del self.connections[viewer_id]

	# WebSocket DAT callbacks

	def OnReceiveText(self, dat: websocketDAT, rowIndex: int, message: str):
		"""
		Called when a text frame message is received. Only text frame messages
		will be handled in this function.

		Args:
			dat: The DAT that received a message
			rowIndex: The row number the message was placed into
			message: A unicode representation of the text
		"""
		data = json.loads(message)

		sig_type = data.get('signalingType', '')
		appstore_key = data.get('key', '')
		sender = data.get('sender', '')

		# Browser component sends 'webrtc_request' (value = component's viewer ID,
		# sender = page's WS identity used to route the Offer/ICE reply back).
		if appstore_key == 'webrtc_request':
			viewer_id = data.get('value', sender)
			ws_sender = sender
			self.Connect(viewer_id, ws_sender)

		# Web component sends 'webrtc_disconnect' (value = component's viewer ID) on removal.
		elif appstore_key == 'webrtc_disconnect':
			viewer_id = data.get('value', sender)
			self.Disconnect(viewer_id)

		elif sig_type == 'Answer':
			# viewerId identifies which WebRTC connection this answer belongs to
			viewer_id = data.get('viewerId', sender)
			conn_id = self.connections.get(viewer_id)
			if conn_id:
				self.webrtcDAT.setRemoteDescription(
					conn_id, 'answer', data['content']['sdp'])

		elif sig_type == 'Ice':
			viewer_id = data.get('viewerId', sender)
			conn_id = self.connections.get(viewer_id)
			if conn_id:
				c = data['content']
				self.webrtcDAT.addIceCandidate(
					conn_id, c['sdpCandidate'], c['sdpMLineIndex'], c['sdpMid'])


	# WebRTC DAT callbacks

	def OnOffer(self, webrtcDAT: webrtcDAT, connectionId: str, localSdp: str):
		webrtcDAT.setLocalDescription(connectionId, 'offer', localSdp, stereo=False)
		ws_sender = self.connection_ws_senders.get(connectionId)
		viewer_id = self.connection_viewer_ids.get(connectionId)
		self.websocketsDAT.sendText(json.dumps({
			'metadata': self.METADATA, 
			'signalingType': 'Offer',
			'sender': 'td_webrtc', 
			'receiver': ws_sender, 
			'viewerId': viewer_id,
			'content': {
				'sdp': localSdp
			}
		}))


	def OnIceCandidate(self, webrtcDAT: webrtcDAT, connectionId: str, candidate: str, lineIndex: int, sdpMid: str):
		ws_sender = self.connection_ws_senders.get(connectionId)
		viewer_id = self.connection_viewer_ids.get(connectionId)
		self.websocketsDAT.sendText(json.dumps({
			'metadata': self.METADATA, 
			'signalingType': 'Ice',
			'sender': 'td_webrtc', 
			'receiver': ws_sender, 
			'viewerId': viewer_id,
			'content': {
				'sdpCandidate': candidate, 
				'sdpMLineIndex': lineIndex, 
				'sdpMid': sdpMid
			}
		}))
