from Plugins.Plugin import PluginDescriptor
from Screens.Screen import Screen
from Components.MenuList import MenuList
from Components.Label import Label
from Components.ActionMap import ActionMap, NumberActionMap
from Components.Pixmap import Pixmap
from Components.AVSwitch import AVSwitch
from Components.ServiceEventTracker import ServiceEventTracker
from Components.Sources.StaticText import StaticText
from Components.ConfigList import ConfigListScreen
from Components.config import config, ConfigSubsection, ConfigBoolean, ConfigSelection, getConfigListEntry
from enigma import eServiceReference, eTimer, iPlayableService, eListboxPythonMultiContent, gFont, RT_HALIGN_LEFT, RT_WRAP, RT_VALIGN_TOP, ePicLoad
from ServiceReference import ServiceReference
from Screens.InfoBarGenerics import InfoBarNotifications, InfoBarSeek
from Screens.VirtualKeyBoard import VirtualKeyBoard
from Screens.MessageBox import MessageBox
from Tools import NumericalTextInput
from Tools.LoadPixmap import LoadPixmap
from Tools.BoundFunction import boundFunction
from Tools.Directories import resolveFilename, SCOPE_PLUGINS
from urllib2 import Request, URLError, HTTPError, urlopen as urlopen2
from httplib import HTTPException
from twisted.web import client
from os import path as os_path, remove as os_remove, mkdir as os_mkdir
import socket
from datetime import date, timedelta
import time


config.plugins.OpenUitzendingGemist = ConfigSubsection()
config.plugins.OpenUitzendingGemist.showpictures = ConfigBoolean(default = True)


def wgetUrl(target):
	std_headers = {
		'User-Agent': 'Mozilla/5.0 (X11; U; Linux x86_64; en-US; rv:1.9.2.6) Gecko/20100627 Firefox/3.6.6',
		'Accept-Charset': 'ISO-8859-1,utf-8;q=0.7,*;q=0.7',
		'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
		'Accept-Language': 'en-us,en;q=0.5',
	}
	outtxt = Request(target, None, std_headers)
	try:
		outtxt = urlopen2(target, timeout = 5).read()
	except (URLError, HTTPException, socket.error):
		return ''
	return outtxt

def wgetUrlRefer(target, refer):
	req = Request(target)
	req.add_header('Referer', refer)
	try:
		r = urlopen2(req)
		outtxt = r.read()
	except:
		outtxt = ''
	return outtxt

def MPanelEntryComponent(channel, text, png):
	res = [ text ]
	res.append((eListboxPythonMultiContent.TYPE_TEXT, 200, 15, 800, 100, 0, RT_HALIGN_LEFT|RT_WRAP|RT_VALIGN_TOP, text))
	res.append((eListboxPythonMultiContent.TYPE_PIXMAP_ALPHATEST, 10, 5, 150, 150, png))
	return res


class MPanelList(MenuList):
	def __init__(self, list, selection = 0, enableWrapAround=True):
		MenuList.__init__(self, list, enableWrapAround, eListboxPythonMultiContent)
		self.l.setFont(0, gFont("Regular", 18))
		self.l.setItemHeight(120)
		self.selection = selection

	def postWidgetCreate(self, instance):
		MenuList.postWidgetCreate(self, instance)
		self.moveToIndex(self.selection)
		
def getShortName(name, serviceref):
	if serviceref.flags & eServiceReference.mustDescent: #Directory			
		pathName = serviceref.getPath()
		p = os.path.split(pathName)
		if not p[1]: #if path ends in '/', p is blank.
			p = os.path.split(p[0])
		return p[1].upper()
	else:
		return name

class UGMediaPlayer(Screen, InfoBarNotifications, InfoBarSeek):
	STATE_IDLE = 0
	STATE_PLAYING = 1
	STATE_PAUSED = 2

	skin = """<screen name="MediaPlayer" flags="wfNoBorder" position="0,380" size="720,160" title="Media player" backgroundColor="transparent">
		<ePixmap position="0,0" pixmap="skin_default/info-bg_mp.png" zPosition="-1" size="720,160" />
		<ePixmap position="29,40" pixmap="skin_default/screws_mp.png" size="665,104" alphatest="on" />
		<ePixmap position="48,70" pixmap="skin_default/icons/mp_buttons.png" size="108,13" alphatest="on" />
		<ePixmap pixmap="skin_default/icons/icon_event.png" position="207,78" size="15,10" alphatest="on" />
		<widget source="session.CurrentService" render="Label" position="230,73" size="360,40" font="Regular;20" backgroundColor="#263c59" shadowColor="#1d354c" shadowOffset="-1,-1" transparent="1">
			<convert type="ServiceName">Name</convert>
		</widget>
		<widget source="session.CurrentService" render="Label" position="580,73" size="90,24" font="Regular;20" halign="right" backgroundColor="#4e5a74" transparent="1">
			<convert type="ServicePosition">Length</convert>
		</widget>
		<widget source="session.CurrentService" render="Label" position="205,129" size="100,20" font="Regular;18" halign="center" valign="center" backgroundColor="#06224f" shadowColor="#1d354c" shadowOffset="-1,-1" transparent="1">
			<convert type="ServicePosition">Position</convert>
		</widget>
		<widget source="session.CurrentService" render="PositionGauge" position="300,133" size="270,10" zPosition="2" pointer="skin_default/position_pointer.png:540,0" transparent="1" foregroundColor="#20224f">
			<convert type="ServicePosition">Gauge</convert>
		</widget>
		<widget source="session.CurrentService" render="Label" position="576,129" size="100,20" font="Regular;18" halign="center" valign="center" backgroundColor="#06224f" shadowColor="#1d354c" shadowOffset="-1,-1" transparent="1">
			<convert type="ServicePosition">Remaining</convert>
		</widget>
		</screen>"""

	def __init__(self, session, service, mediatype):
		Screen.__init__(self, session)
		self.skinName = "MoviePlayer"
		InfoBarNotifications.__init__(self)
		if mediatype == 'rtl':
			InfoBarSeek.__init__(self)
		self.session = session
		self.service = service
		self.screen_timeout = 3000
		self.mediatype = mediatype
		self.__event_tracker = ServiceEventTracker(screen = self, eventmap =
			{
				iPlayableService.evStart: self.__serviceStarted,
				iPlayableService.evSeekableStatusChanged: self.__seekableStatusChanged,
				iPlayableService.evEOF: self.__evEOF,
			})
		self["actions"] = ActionMap(["OkCancelActions", "InfobarSeekActions", "MediaPlayerActions", "MovieSelectionActions"],
		{
				"ok": self.ok,
				"cancel": self.leavePlayer,
				"stop": self.handleLeave,
				"showEventInfo": self.showVideoInfo,
			}, -2)
		self.hidetimer = eTimer()
		self.hidetimer.timeout.get().append(self.ok)
		self.returning = False
		self.state = self.STATE_PLAYING
		self.lastseekstate = self.STATE_PLAYING
		self.onPlayStateChanged = [ ]
		self.play()
		self.onClose.append(self.__onClose)

	def __seekableStatusChanged(self):
		if self.mediatype != 'rtl':
			return
		if not self.isSeekable():
			self["SeekActions"].setEnabled(False)
			self.setSeekState(self.STATE_PLAYING)
		else:
			self["SeekActions"].setEnabled(True)

	def __onClose(self):
		self.session.nav.stopService()

	def __evEOF(self):
		self.handleLeave()

	def __setHideTimer(self):
		self.hidetimer.start(self.screen_timeout)

	def showInfobar(self):
		self.show()
		if self.state == self.STATE_PLAYING:
			self.__setHideTimer()
		else:
			pass

	def hideInfobar(self):
		self.hide()
		self.hidetimer.stop()

	def ok(self):
		if self.shown:
			self.hideInfobar()
		else:
			self.showInfobar()

	def showVideoInfo(self):
		if self.shown:
			self.hideInfobar()

	def playService(self, newservice):
		if self.state != self.STATE_IDLE:
			self.stopCurrent()
		self.service = newservice
		self.play()

	def play(self):
		if self.state == self.STATE_PAUSED:
			if self.shown:
				self.__setHideTimer()
		self.state = self.STATE_PLAYING
		self.session.nav.playService(self.service)
		if self.shown:
			self.__setHideTimer()

	def stopCurrent(self):
		self.session.nav.stopService()
		self.state = self.STATE_IDLE

	def __serviceStarted(self):
		self.state = self.STATE_PLAYING
		self.__seekableStatusChanged()

	def handleLeave(self):
		self.close()

	def leavePlayer(self):
		self.session.openWithCallback(self.leavePlayerOnExitCallback, MessageBox, _("Exit movie player?"), simple=True)

	def leavePlayerOnExitCallback(self, answer):
		if answer == True:
			self.handleLeave()

	def doEofInternal(self, playing):
		if not self.execing:
			return
		if not playing :
			return
		self.handleLeave()

	def lockShow(self):
		return

	def unlockShow(self):
		return

class OpenUgConfigureScreen(Screen, ConfigListScreen):
	def __init__(self, session):
		self.skin = """
				<screen position="center,center" size="400,100" title="">
					<widget name="config" position="10,10"   size="e-20,e-10" scrollbarMode="showOnDemand" />
				</screen>"""
		self.session = session
		Screen.__init__(self, session)

		self.list = []
		ConfigListScreen.__init__(self, self.list, session = self.session)

		self["actions"] = ActionMap(["SetupActions"],
		{
			"ok": self.keyGo,
			"cancel": self.keyCancel,
		}, -2)

		self["config"].list = self.list
		self.list.append(getConfigListEntry(_("Show pictures"), config.plugins.OpenUitzendingGemist.showpictures))
		self["config"].l.setList(self.list)

		self.onLayoutFinish.append(self.layoutFinished)

	def layoutFinished(self):
		self.setTitle(_("Open Uitzending Gemist options"))

	def keyGo(self):
		for x in self["config"].list:
			x[1].save()
		self.close()

	def keyCancel(self):
		for x in self["config"].list:
			x[1].cancel()
		self.close()

class OpenUgSetupScreen(Screen):
	def __init__(self, session):
		self.skin = """
				<screen position="center,center" size="400,450" title="">
					<widget name="menu" position="10,10"   size="e-20,e-130" scrollbarMode="showOnDemand" />
					<widget name="info" position="10,e-125" size="e-20,150" halign="center" font="Regular;22" />
				</screen>"""
		self.session = session
		Screen.__init__(self, session)

		self["key_red"] = StaticText(_("Cancel"))
		self["key_green"] = StaticText(_("OK"))

		self.lastservice = session.nav.getCurrentlyPlayingServiceReference()

		self["actions"] = ActionMap(["SetupActions"],
		{
			"ok": self.keyGo,
			"cancel": self.keyCancel,
		}, -2)

		self.imagedir = '/tmp/openUgImg/'

		self["info"] = Label(_("Open Uitzending Gemist\n\nBased on Xtrend code"))

		self.mmenu= []
		self.mmenu.append((_("UG Uitgelicht"), 'uitgelicht'))
		self.mmenu.append((_("UG Popular"), 'pop'))
		self.mmenu.append((_("UG Gemist"), 'ugback'))
		self.mmenu.append((_("RTL XL A-Z"), 'rtl'))
		self.mmenu.append((_("RTL XL Gemist"), 'rtlback'))
		self.mmenu.append((_("SBS6 Gemist"), 'sbs6'))
		self.mmenu.append((_("Veronica Gemist"), 'veronica'))
		self.mmenu.append((_("NET5 Gemist"), 'net5'))
		self.mmenu.append((_("Setup"), 'setup'))
		self["menu"] = MenuList(self.mmenu)

		self.onLayoutFinish.append(self.layoutFinished)

	def loadUrl(self, url, sub):
		try:
			lines = open(url).readlines()
			for x in lines:
				if sub in x.lower():
					return True
		except:
			return False
		return False

	def layoutFinished(self):
		self.setTitle('Open Uitzending Gemist')

	def keyGo(self):
		selection = self["menu"].l.getCurrentSelection()
		if selection is not None:
			if selection[1] == 'uitgelicht':
				self.session.open(OpenUg, selection[1])
			elif selection[1] == 'pop':
				self.session.open(OpenUg, selection[1])
			elif selection[1] == 'ugback':
				self.session.open(UgDaysBackScreen)
			elif selection[1] == 'rtl':
				self.session.open(OpenUg, selection[1])
			elif selection[1] == 'rtlback':
				self.session.open(DaysBackScreen)
			elif selection[1] == 'rsearch':
				self.isRtl = True
				self.session.open(OpenUg, selection[1])
			elif selection[1] == 'net5':
				self.session.open(OpenUg, selection[1])
			elif selection[1] == 'sbs6':
				self.session.open(OpenUg, selection[1])
			elif selection[1] == 'veronica':
				self.session.open(OpenUg, selection[1])
			elif selection[1] == 'setup':
				self.session.open(OpenUgConfigureScreen)

	def keyCancel(self):
		self.removeFiles(self.imagedir)
		if self.lastservice is not None:
			self.session.nav.playService(self.lastservice)
		self.close()

	def removeFiles(self, targetdir):
		import os
		for root, dirs, files in os.walk(targetdir):
			for name in files:
				os.remove(os.path.join(root, name))


class DaysBackScreen(Screen):
	def __init__(self, session):
		self.skin = """
				<screen position="center,center" size="400,400" title="">
					<widget name="menu" position="10,10"   size="e-20,e-10" scrollbarMode="showOnDemand" />
				</screen>"""
		self.session = session
		Screen.__init__(self, session)

		self["key_red"] = StaticText(_("Cancel"))
		self["key_green"] = StaticText(_("OK"))

		self["actions"] = ActionMap(["SetupActions"],
		{
			"ok": self.keyGo,
			"cancel": self.keyCancel,
		}, -2)

		self.mmenu= []
		count = 0
		now = date.today()
		while count < 15:
			if count == 0:
				self.mmenu.append((_("Today"), now.strftime('%Y%m%d')))
			else:
				self.mmenu.append(((now.strftime("%A")), now.strftime('%Y%m%d')))
			now = now - timedelta(1)
			count += 1
		self["menu"] = MenuList(self.mmenu)

		self.onLayoutFinish.append(self.layoutFinished)

	def layoutFinished(self):
		self.setTitle(_("RTL Number of days back"))

	def keyGo(self):
		selection = self["menu"].l.getCurrentSelection()
		self.session.open(OpenUg, ['rtlback', selection[1]])

	def keyCancel(self):
		self.close()

class UgDaysBackScreen(Screen):
	def __init__(self, session):
		self.skin = """
				<screen position="center,center" size="400,400" title="">
					<widget name="menu" position="10,10"   size="e-20,e-10" scrollbarMode="showOnDemand" />
				</screen>"""
		self.session = session
		Screen.__init__(self, session)

		self["key_red"] = StaticText(_("Cancel"))
		self["key_green"] = StaticText(_("OK"))

		self["actions"] = ActionMap(["SetupActions"],
		{
			"ok": self.keyGo,
			"cancel": self.keyCancel,
		}, -2)

		self.mmenu= []
		count = 0
		now = date.today()
		while count < 8:
			if count == 0:
				self.mmenu.append((_("Today"), count + 128))
			else:
				self.mmenu.append(((now.strftime("%A")), count + 128))
			now = now - timedelta(1)
			count += 1
		self["menu"] = MenuList(self.mmenu)

		self.onLayoutFinish.append(self.layoutFinished)

	def layoutFinished(self):
		self.setTitle(_("NPO Number of days back"))

	def keyGo(self):
		selection = self["menu"].l.getCurrentSelection()
		self.session.open(OpenUg, selection[1])

	def keyCancel(self):
		self.close()

class OpenUg(Screen):

	UG_PROGDATE = 0
	UG_PROGNAME = 1
	UG_SHORT_DESCR = 2
	UG_CHANNELNAME = 3
	UG_STREAMURL = 4
	UG_ICON = 5
	UG_ICONTYPE = 6
	UG_LEVEL_ALL = 0
	UG_LEVEL_SERIE = 1
	UG_LEVEL_SEASON = 2
	MAX_PIC_PAGE = 5

	TIMER_CMD_START = 0
	TIMER_CMD_VKEY = 1
	UG_BASE_URL = "http://hbbtv.distributie.publiekeomroep.nl"
	HBBTV_UG_BASE_URL = UG_BASE_URL + "/nu/ajax/action/"
	RTL_BASE_URL = "http://www.rtl.nl/system/s4m/vfd/version=1/d=pc/output=json"
	SBS_BASE_URL = "http://plus-api.sbsnet.nl"
	EMBED_BASE_URL = "http://embed.kijk.nl/?width=868&height=488&video="

	def __init__(self, session, cmd):
		self.skin = """
				<screen position="80,70" size="e-160,e-110" title="">
					<widget name="list" position="0,0" size="e-0,e-0" scrollbarMode="showOnDemand" transparent="1" zPosition="2"/>
					<widget name="thumbnail" position="0,0" size="150,150" alphatest="on" />
					<widget name="chosenletter" position="10,10" size="e-20,150" halign="center" font="Regular;30" foregroundColor="#FFFF00" />
				</screen>"""
		self.session = session
		Screen.__init__(self, session)

		self["thumbnail"] = Pixmap()
		self["thumbnail"].hide()

		self.cbTimer = eTimer()
		self.cbTimer.callback.append(self.timerCallback)

		self.Details = {}
		self.pixmaps_to_load = []
		self.picloads = {}
		self.color = "#33000000"
		
		self.numericalTextInput = NumericalTextInput.NumericalTextInput(mapping=NumericalTextInput.MAP_SEARCH_UPCASE)
		self["chosenletter"] = Label("")
		self["chosenletter"].visible = False 

		self.page = 0
		self.numOfPics = 0
		self.isRtl = False
		self.isRtlBack = False
		self.isSbs = False
		self.channel = ''
		self.level = self.UG_LEVEL_ALL
		self.cmd = cmd
		self.timerCmd = self.TIMER_CMD_START

		self.png = LoadPixmap(resolveFilename(SCOPE_PLUGINS, "Extensions/OpenUitzendingGemist/oe-alliance.png"))

		self.tmplist = []
		self.mediaList = []

		self.imagedir = "/tmp/openUgImg/"
		if (os_path.exists(self.imagedir) != True):
			os_mkdir(self.imagedir)

		self["list"] = MPanelList(list = self.tmplist, selection = 0)
		self.list = self["list"]
		self.updateMenu()
		self["actions"] = ActionMap(["WizardActions", "MovieSelectionActions", "DirectionActions"],
		{
			"up": self.key_up,
			"down": self.key_down,
			"left": self.key_left,
			"right": self.key_right,
			"ok": self.go,
			"back": self.Exit,
		}
		, -1)
		self["NumberActions"] = NumberActionMap(["NumberActions", "InputAsciiActions"],
			{
				"gotAsciiCode": self.keyAsciiCode,
				"0": self.keyNumberGlobal,
				"1": self.keyNumberGlobal,
				"2": self.keyNumberGlobal,
				"3": self.keyNumberGlobal,
				"4": self.keyNumberGlobal,
				"5": self.keyNumberGlobal,
				"6": self.keyNumberGlobal,
				"7": self.keyNumberGlobal,
				"8": self.keyNumberGlobal,
				"9": self.keyNumberGlobal
			}) 
		self.onLayoutFinish.append(self.layoutFinished)
		self.cbTimer.start(10)
		
	def keyNumberGlobal(self, number):
		unichar = self.numericalTextInput.getKey(number)
		charstr = unichar.encode("utf-8")
		if len(charstr) == 1:
			self.moveToChar(charstr[0], self["chosenletter"])
				
	def keyAsciiCode(self):
		unichar = unichr(getPrevAsciiCode())
		charstr = unichar.encode("utf-8")
		if len(charstr) == 1:
			self.moveToString(charstr[0], self["chosenletter"])
			
	def moveToChar(self, char, lbl=None):
		self._char = char
		self._lbl = lbl
		if lbl:			
			lbl.setText(self._char)
			lbl.visible = True
		self.moveToCharTimer = eTimer()
		self.moveToCharTimer.callback.append(self._moveToChrStr)
		self.moveToCharTimer.start(1000, True) #time to wait for next key press to decide which letter to use...

	def moveToString(self, char, lbl=None):
		self._char = self._char + char.upper()
		self._lbl = lbl
		if lbl:			
			lbl.setText(self._char)
			lbl.visible = True
		self.moveToCharTimer = eTimer()
		self.moveToCharTimer.callback.append(self._moveToChrStr)
		self.moveToCharTimer.start(1000, True) #time to wait for next key press to decide which letter to use...

	def _moveToChrStr(self):
		currentIndex = self["list"].getSelectionIndex()
		found = False
		if currentIndex < (len(self.mediaList) - 1):
			itemsBelow = self.mediaList[currentIndex + 1:]
			#first search the items below the selection
			for index, item in enumerate(itemsBelow):
				itemName = self.mediaList[index][self.UG_PROGNAME]
				if len(self._char) == 1 and itemName.startswith(self._char):
					found = True
					self["list"].moveToIndex(index)
					break
				elif len(self._char) > 1 and itemName.find(self._char) >= 0:
					found = True
					self["list"].moveToIndex(index)
					break
		if found == False and currentIndex > 0:
			itemsAbove = self.mediaList[1:currentIndex]
			#first item (0) points parent folder - no point to include
			for index, item in enumerate(itemsAbove):
				itemName = self.mediaList[index][self.UG_PROGNAME]
				if len(self._char) == 1 and itemName.startswith(self._char):
					found = True
					self["list"].moveToIndex(index)
					break
				elif len(self._char) > 1 and itemName.find(self._char) >= 0:
					found = True
					self["list"].moveToIndex(index)
					break
		self._char = ''
		if self._lbl:
			self._lbl.visible = False

	def layoutFinished(self):
		if self.cmd == None or self.cmd == '':
			self.setTitle("Open Uitzending Gemist")
		elif type(self.cmd) == list:
			title = self.cmd[0]
			self.setTitle("Open Uitzending Gemist " + title)
		elif 'sbs6' == self.cmd or 'veronica' == self.cmd or 'net5' == self.cmd or 'rtl' == self.cmd:
			self.setTitle("Open Uitzending Gemist " + self.cmd)
		else:
			self.setTitle("Open Uitzending Gemist NPO")

	def updatePage(self):
		if self.page != self["list"].getSelectedIndex() / self.MAX_PIC_PAGE:
			self.page = self["list"].getSelectedIndex() / self.MAX_PIC_PAGE
			self.loadPicPage()

	def key_up(self):
		self["list"].up()
		self.updatePage()

	def key_down(self):
		self["list"].down()
		self.updatePage()

	def key_left(self):
		self["list"].pageUp()
		self.updatePage()

	def key_right(self):
		self["list"].pageDown()
		self.updatePage()

	def getThumbnailName(self, x):
		if self.isRtl:
			if x[self.UG_ICON]:
				return ""
			else:
				return ""
		return str(x[self.UG_STREAMURL]) + str(x[self.UG_ICONTYPE])

	def updateMenu(self):
		self.tmplist = []
		if len(self.mediaList) > 0:
			pos = 0
			for x in self.mediaList:
				self.tmplist.append(MPanelEntryComponent(channel = x[self.UG_CHANNELNAME], text = (x[self.UG_PROGNAME] + '\n' + x[self.UG_PROGDATE] + '\n' + x[self.UG_SHORT_DESCR]), png = self.png))
				tmp_icon = self.getThumbnailName(x)
				thumbnailFile = self.imagedir + tmp_icon
				self.pixmaps_to_load.append(tmp_icon)

				if not self.Details.has_key(tmp_icon):
					self.Details[tmp_icon] = { 'thumbnail': None}

				if x[self.UG_ICON] != '':
					if (os_path.exists(thumbnailFile) == True):
						self.fetchFinished(True, picture_id = tmp_icon, failed = False)
					else:
						if config.plugins.OpenUitzendingGemist.showpictures.value:
							client.downloadPage(x[self.UG_ICON], thumbnailFile).addCallback(self.fetchFinished, tmp_icon).addErrback(self.fetchFailed, tmp_icon)
				pos += 1
			self["list"].setList(self.tmplist)

	def Exit(self):
		doExit = False
		if self.level == self.UG_LEVEL_ALL:
			doExit = True
		else:
			if self.isRtl:
				if self.isRtlBack:
					doExit = True
				else:
					doExit = True
			else:
				doExit = True
		if doExit:
			self.close()

	def clearList(self):
		elist = []
		self["list"].setList(elist)
		self.mediaList = []
		self.pixmaps_to_load = []
		self.page = 0

	def setupCallback(self, retval = None):
		if retval == 'cancel' or retval is None:
			return
			
		if type(retval) == list:
			if retval[0] == 'sbs':
				tmp = retval[1]
				self.clearList()
				self.isSbs = True
				self.channel = retval[2]
				self.level = self.UG_LEVEL_SERIE
				self.sbsGetEpisodeList(self.mediaList, tmp)
				if len(self.mediaList) == 0:
					self.mediaProblemPopup()
				else:
					self.updateMenu()
			elif retval[0] == 'rtlseason':
				tmp = retval[1]
				self.clearList()
				self.isRtl = True
				self.level = self.UG_LEVEL_SEASON
				self.getRTLMediaDataSeason(self.mediaList, tmp)
				if len(self.mediaList) == 0:
					self.mediaProblemPopup()
				else:
					self.updateMenu()
			elif retval[0] == 'rtlepisode':
				tmp = retval[1]
				Skey = retval[2]
				self.clearList()
				self.isRtl = True
				self.level = self.UG_LEVEL_SERIE
				self.getRTLSerie(self.mediaList, tmp, Skey)
				if len(self.mediaList) == 0:
					self.mediaProblemPopup()
				else:
					self.updateMenu()
			elif retval[0] == 'rtlback':
				self.clearList()
				self.isRtl = True
				self.isRtlBack = True
				self.level = self.UG_LEVEL_SERIE
				self.getRTLMediaDataBack(self.mediaList, retval[1])
				if len(self.mediaList) == 0:
					self.mediaProblemPopup()
				else:
					self.updateMenu()

		elif retval == 'uitgelicht':
			self.clearList()
			self.level = self.UG_LEVEL_SERIE
			offset = 0
			while 1:
				self.getMediaData(self.mediaList, self.HBBTV_UG_BASE_URL + "must_see/offset/%d/numrows/24?XHRUrlAddOn=1" % (offset))
				if len(self.mediaList) == 0:
					self.mediaProblemPopup()
					break
				if offset + 24 != len(self.mediaList):
					break
				offset += 24
			self.updateMenu()
		elif retval == 'pop':
			self.clearList()
			self.level = self.UG_LEVEL_SERIE
			offset = 0
			while 1:
				self.getMediaData(self.mediaList, self.HBBTV_UG_BASE_URL + "popular/offset/%d/numrows/24?XHRUrlAddOn=1" % (offset))
				if len(self.mediaList) == 0:
					self.mediaProblemPopup()
					break
				if offset + 24 != len(self.mediaList):
					break
				offset += 24
			self.updateMenu()
		elif retval == 'rsearch':
			self.isRtl = True
			self.timerCmd = self.TIMER_CMD_VKEY
			self.cbTimer.start(10)
		elif retval == 'rtl':
			self.clearList()
			self.isRtl = True
			self.level = self.UG_LEVEL_ALL
			self.getRTLMediaData(self.mediaList, "/fun=az/fmt=smooth")
			if len(self.mediaList) == 0:
				self.mediaProblemPopup()
			else:
				self.updateMenu()
		elif retval == 'net5':
			self.clearList()
			self.isSbs = True
			self.channel = retval
			self.level = self.UG_LEVEL_ALL
			self.sbsGetProgramList(self.mediaList)
			if len(self.mediaList) == 0:
				self.mediaProblemPopup()
			else:
				self.updateMenu()
		elif retval == 'sbs6':
			self.clearList()
			self.isSbs = True
			self.channel = retval
			self.level = self.UG_LEVEL_ALL
			self.sbsGetProgramList(self.mediaList)
			if len(self.mediaList) == 0:
				self.mediaProblemPopup()
			else:
				self.updateMenu()
		elif retval == 'veronica':
			self.clearList()
			self.isSbs = True
			self.channel = retval
			self.level = self.UG_LEVEL_ALL
			self.sbsGetProgramList(self.mediaList)
			if len(self.mediaList) == 0:
				self.mediaProblemPopup()
			else:
				self.updateMenu()
		else:
			if retval >= 128:
				retval -=  128
				now = int(time.time())
				worktime =  '%s' % (time.strftime("%H:%M:%S", time.localtime()))
				wtime = worktime.split(":")
				if int(wtime[0]) < 6:
					t = int(wtime[0]) + (24 - 6)
				else:
					t = int(wtime[0]) - 6
				t = (t * 3600) + int(wtime[1]) * 60 + int(wtime[2]) + 1
				startime = int(now - t)
				day = 3600 * 24
				if (retval > 0):
					day *= retval
					startime -= day
					now = startime + (3600 * 24)
				self.clearList()
				self.level = self.UG_LEVEL_SERIE
				offset = 0
				while 1:
					self.getMediaData(self.mediaList, self.HBBTV_UG_BASE_URL + "epg/timeStart/%d/timeEnd/%d/day/%d/offset/%d/numrows/24?XHRUrlAddOn=1" % (startime, now, retval, offset))
					if len(self.mediaList) == 0:
						self.mediaProblemPopup()
						break
					if offset + 24 != len(self.mediaList):
						break
					offset += 24
				self.updateMenu()
				return

	def timerCallback(self):
		self.cbTimer.stop()
		if self.timerCmd == self.TIMER_CMD_START:
			self.setupCallback(self.cmd)
		elif self.timerCmd == self.TIMER_CMD_VKEY:
			self.session.openWithCallback(self.keyboardCallback, VirtualKeyBoard, title = (_("Search term")), text = "")

	def keyboardCallback(self, callback = None):
		if callback is not None and len(callback):
			self.clearList()
			self.level = self.UG_LEVEL_SERIE
			if self.isRtl == True:
				self.getRTLSerie(self.mediaList, "search.php?q=*" + callback + "*")
				self.updateMenu()
			if len(self.mediaList) == 0:
				self.session.openWithCallback(self.close, MessageBox, _("No items matching your search criteria were found"), MessageBox.TYPE_ERROR, timeout=5, simple = True)
		else:
			self.close()

	def mediaProblemPopup(self):
		self.session.openWithCallback(self.close, MessageBox, _("There was a problem retrieving the media list"), MessageBox.TYPE_ERROR, timeout=5, simple = True)

	def fetchFailed(self, string, picture_id):
		self.fetchFinished(False, picture_id, failed = True)

	def fetchFinished(self, x, picture_id, failed = False):
		if failed:
			return
		else:
			thumbnailFile = self.imagedir + str(picture_id)
		sc = AVSwitch().getFramebufferScale()
		if (os_path.exists(thumbnailFile) == True):
			start = self.page * self.MAX_PIC_PAGE
			end  = (self.page * self.MAX_PIC_PAGE) + self.MAX_PIC_PAGE
			count = 0
			for x in self.mediaList:
				if count >= start and count < end:
					if self.getThumbnailName(x) == picture_id:
						self.picloads[picture_id] = ePicLoad()
						self.picloads[picture_id].PictureData.get().append(boundFunction(self.finish_decode, picture_id))
						self.picloads[picture_id].setPara((150, 150, sc[0], sc[1], False, 1, "#00000000"))
						self.picloads[picture_id].startDecode(thumbnailFile)
				count += 1
				if count > end:
					break
		else:
			self.pixmaps_to_load.append(picture_id)
			self.fetchFinished(False, picture_id, failed = True)

	def loadPicPage(self):
		self.Details = {}
		self.updateMenu()

	def finish_decode(self, picture_id, info):
		ptr = self.picloads[picture_id].getData()
		thumbnailFile = self.imagedir + str(picture_id)
		if ptr != None:
			if self.Details.has_key(picture_id):
				self.Details[picture_id]["thumbnail"] = ptr
		self.tmplist = []
		pos = 0
		for x in self.mediaList:
			if self.Details[self.getThumbnailName(x)]["thumbnail"] is not None:
				self.tmplist.append(MPanelEntryComponent(channel = x[self.UG_CHANNELNAME], text = (x[self.UG_PROGNAME] + '\n' + x[self.UG_PROGDATE] + '\n' + x[self.UG_SHORT_DESCR]), png = self.Details[self.getThumbnailName(x)]["thumbnail"]))
			else:
				self.tmplist.append(MPanelEntryComponent(channel = x[self.UG_CHANNELNAME], text = (x[self.UG_PROGNAME] + '\n' + x[self.UG_PROGDATE] + '\n' + x[self.UG_SHORT_DESCR]), png = self.png))
			pos += 1
		self["list"].setList(self.tmplist)

	def go(self):
		if len(self.mediaList) == 0 or self["list"].getSelectionIndex() > len(self.mediaList) - 1:
			return
		if self.isSbs:
			if self.level == self.UG_LEVEL_ALL:
				tmp = self.mediaList[self["list"].getSelectionIndex()][self.UG_STREAMURL]
				self.session.open(OpenUg, ['sbs' , tmp , self.channel])
			elif self.level == self.UG_LEVEL_SERIE:
				tmp = self.sbsGetMediaUrl(self.mediaList[self["list"].getSelectionIndex()][self.UG_STREAMURL])
				if tmp != '':
					myreference = eServiceReference(4097, 0, tmp)
					myreference.setName(self.mediaList[self["list"].getSelectionIndex()][self.UG_PROGNAME])
					self.session.open(UGMediaPlayer, myreference, 'sbs')
		elif self.isRtl:
			if self.level == self.UG_LEVEL_ALL:
				tmp = self.mediaList[self["list"].getSelectionIndex()][self.UG_STREAMURL]
				self.session.open(OpenUg, ['rtlseason' , tmp])
			elif self.level == self.UG_LEVEL_SEASON:
				tmp = self.mediaList[self["list"].getSelectionIndex()][self.UG_STREAMURL]
				self.session.open(OpenUg, ['rtlepisode' , tmp[0], tmp[1]])
			elif self.level == self.UG_LEVEL_SERIE:
				tmp = self.getRTLStream(self.mediaList[self["list"].getSelectionIndex()][self.UG_STREAMURL])
				if tmp != '':
					myreference = eServiceReference(4097, 0, tmp)
					myreference.setName(self.mediaList[self["list"].getSelectionIndex()][self.UG_PROGNAME])
					self.session.open(UGMediaPlayer, myreference, 'rtl')
				else:
					self.session.openWithCallback(self.close, MessageBox, _("Voor deze aflevering moet waarschijnlijk betaald worden."), MessageBox.TYPE_ERROR, timeout=5, simple = True)
		else:
			self.doUGPlay()

	def doUGPlay(self):
		out = wgetUrl(self.UG_BASE_URL + "/nu/bekijk/context/bekijk_gemist/trm_id/%s?XHRUrlAddOn=1" % (self.mediaList[self["list"].getSelectionIndex()][self.UG_STREAMURL]))
		if out !='':
			url = ''
			tmp = out.split('\n')
			for x in tmp:
				if 'fetchLinkAndStart' in x:
					tmp =  x.split("('")[1].split("'")[0]
					tmp = wgetUrl(self.UG_BASE_URL + tmp)
					tmp = tmp.replace('\/', '/')
					url = tmp.split("stream_link\":\"")[1].split("\",")[0]
					break
			if url != '':
				myreference = eServiceReference(4097, 0, url)
				myreference.setName(self.mediaList[self["list"].getSelectionIndex()][self.UG_PROGNAME])
				self.session.open(UGMediaPlayer, myreference, 'npo')

	def getRTLStream(self, url):
		uuid = url
		data = wgetUrl('http://www.rtl.nl/system/s4m/xldata/ux/'+ url +'?context=rtlxl&d=pc&fmt=adaptive&version=3')
		state = 0
		url = ''
		name = ''
		icon = ''
		tmp = '<component_uri>'
		if tmp in data:
			url = data.split(tmp)[1].split('</component_uri>')[0]
			url = 'http://pg.us.rtl.nl/rtlxl/network/ipad/progressive' + url + '.ssm/' + uuid + '.mp4'
			return url
		else:
			return ''

	def getRTLSerie(self, weekList, url, Skey):
		url = self.RTL_BASE_URL + '/ak='+ url +'/sk='+ Skey +'/pg=1'
		data = wgetUrl(url)
		tmp = '\"schedule\":'
		if tmp in data:
			data = data.split(tmp)
			scheduledata = data[1].split('},{')
			data = data[0]
		tmp = '\"material\":'
		if tmp in data:
			data = data.split(tmp)
			uuiddata = data[1].split('},{')
			data = data[0]
		tmp = '\"episodes\":'
		if tmp in data:
			data = data.split(tmp)
			episode = data[1].split('\"key\"')
			data = data[0]
		tmp = '\"seasons\":'
		if tmp in data:
			data = data.split(tmp)
			seasons = data[1].split('\"key\"')
			data = data[0]
		tmp = '\"abstracts\":'
		if tmp in data:
			data = data.split(tmp)
			abstract = data[1].split('\"key\"')
			data = data[0]
		state = 0
		name = ''
		short = ''
		icon = ''
		stream = ''
		date = ''
		channel = ''
		for line in episode:
			if state == 0:
				if "\"name\":" in line:
					state = 1
			if state == 1:
				tmp = "\"name\":\""
				if tmp in line:
					name = line.split(tmp)[1].split('"')[0]
				tmp = '\"synopsis\":\"'
				if tmp in line:
					short = line.split(tmp)[1].split('\"')[0]
				key = line.split('\"')[1]
				key = "\"episode_key\":\"" + key
				for line in uuiddata:
					if key in line and '\"classname\":\"uitzending\"' in line:
						tmp = "\"uuid\":\""
						if tmp in line:
							stream = line.split(tmp)[1].split('"')[0]
						tmp = '\"station\":\"'
						if tmp in line:
							channel = line.split(tmp)[1].split('\"')[0]
						tmp = '\"duration\":\"'
						if tmp in line:
							date = line.split(tmp)[1].split('\"')[0]
				icon_type = icon
				if stream != '':
					weekList.append((date, name, short, channel, stream, icon, icon_type, True))
				name = ''
				short = ''
				icon = ''
				stream = ''
				date = ''
				channel = ''
				state = 0
		
	def getRTLMediaDataSeason(self, weekList, url):
		data = wgetUrl(self.RTL_BASE_URL + '/fun=getseasons/ak=' + url)
		tmp = '\"schedule\":'
		if tmp in data:
			data = data.split(tmp)
			scheduledata = data[1].split('},{')
			data = data[0]
		tmp = '\"material\":'
		if tmp in data:
			data = data.split(tmp)
			uuiddata = data[1].split('},{')
			data = data[0]
		tmp = '\"episodes\":'
		if tmp in data:
			data = data.split(tmp)
			episode = data[1].split('\"key\"')
			data = data[0]
		tmp = '\"seasons\":'
		if tmp in data:
			data = data.split(tmp)
			seasons = data[1].split('\"key\"')
			data = data[0]
		tmp = '\"abstracts\":'
		if tmp in data:
			data = data.split(tmp)
			abstract = data[1].split('\"key\"')
			data = data[0]
		state = 0
		name = ''
		short = ''
		icon = ''
		stream = ''
		date = ''
		channel = ''
		for line in seasons:
			if state == 0:
				if "\"name\"" in line:
					state = 1
			if state == 1:
				stream = line.split('\"')[1].replace(' ','')
				tmp = ".png"
				icon_type = ''
				if tmp in line:
					tmp = "\"proglogo\":\""
					icon_type = icon
				tmp = '\"synopsis\":\"'
				if tmp in line:
					short = line.split(tmp)[1].split('\"')[0]
				tmp = '\"station\":\"'
				if tmp in line:
					channel = line.split(tmp)[1].split('\"')[0]
				tmp = '\"abstract_key\":\"'
				if tmp in line:
					stream = [(line.split(tmp)[1].split('\"')[0]) , stream]
				tmp = "\"name\":\""
				if tmp in line:
					name = line.split(tmp)[1].split('"')[0]
				weekList.append((date, name, short, channel, stream, icon, icon_type, True))
				state = 0

	def getRTLMediaData(self, weekList, url):
		data = wgetUrl(self.RTL_BASE_URL + url)
		data = data.split('\"key\"')
		state = 0
		name = ''
		short = ''
		icon = ''
		stream = ''
		date = ''
		channel = ''
		for line in data:
			if state == 0:
				if "\"name\"" in line:
					state = 1
			if state == 1:
				stream = line.split('\"')[1].replace(' ','')
				tmp = ".png"
				if tmp in line:
					tmp = "\"proglogo\":\""
					icon_type = icon
				tmp = '\"synopsis\":\"'
				if tmp in line:
					short = line.split(tmp)[1].split('\"')[0]
				tmp = '\"station\":\"'
				if tmp in line:
					channel = line.split(tmp)[1].split('\"')[0]
				tmp = "\"name\":\""
				if tmp in line:
					name = line.split(tmp)[1].split('"')[0]
				weekList.append((date, name, short, channel, stream, icon, icon_type, True))
				state = 0

	def getRTLMediaDataBack(self, weekList, days):
		url = self.RTL_BASE_URL + "/fun=catchup/pg=1/bcdate=%s/station=RTL4,RTL5,RTL7,RTL8" % (days)
		data = wgetUrl(url)
		tmp = '\"schedule\":'
		if tmp in data:
			data = data.split(tmp)
			scheduledata = data[1].split('},{')
			data = data[0]
		tmp = '\"material\":'
		if tmp in data:
			data = data.split(tmp)
			uuiddata = data[1].split('},{')
			data = data[0]
		tmp = '\"episodes\":'
		if tmp in data:
			data = data.split(tmp)
			episode = data[1].split('\"key\"')
			data = data[0]
		tmp = '\"seasons\":'
		if tmp in data:
			data = data.split(tmp)
			seasons = data[1].split('\"key\"')
			data = data[0]
		tmp = '\"abstracts\":'
		if tmp in data:
			data = data.split(tmp)
			abstract = data[1].split('\"key\"')
			data = data[0]
		state = 0
		name = ''
		short = ''
		icon = ''
		stream = ''
		date = ''
		channel = ''
		akey = ''
		ekey = ''
		for line in scheduledata:
			if state == 0:
				if "\"episode_key\":" in line:
					state = 1
			if state == 1:
				tmp = "\"episode_key\":\""
				if tmp in line:
					ekey = line.split(tmp)[1].split('"')[0]
				tmp = '\"station\":\"'
				if tmp in line:
					channel = line.split(tmp)[1].split('"')[0]
				if ekey != '':
					state = 2
			if state == 2:
				for line in episode:
					if ekey in line:
						tmp = "\"name\":\""
						if tmp in line:
							date = line.split(tmp)[1].split('"')[0]
						tmp = '\"synopsis\":\"'
						if tmp in line:
							short = line.split(tmp)[1].split('\"')[0]
				ekey = "\"episode_key\":\"" + ekey
				for line in uuiddata:
					if ekey in line:
						tmp = "\"uuid\":\""
						if tmp in line:
							stream = line.split(tmp)[1].split('"')[0]
						tmp = '\"duration\":\"'
						if tmp in line:
							date = (line.split(tmp)[1].split('\"')[0] + ' | ' + date)
						tmp = "\"abstract_key\":\""
						if tmp in line:
							akey = line.split(tmp)[1].split('"')[0]
				for line in abstract:
					if akey in line:
						tmp = "\"name\":\""
						if tmp in line:
							name = line.split(tmp)[1].split('"')[0]
				icon_type = icon
				weekList.append((date, name, short, channel, stream, icon, icon_type, True))
				state = 0

	def getMediaData(self, weekList, url):
		data = wgetUrl(url)
		state = 0
		short = ''
		name = ''
		date = ''
		stream = ''
		channel = ''
		icon = ''
		tmp = "<div class=\"vid\""
		i = data.count(tmp)
		j = 1
		data = data.split(tmp)
		while j<i:
			short = ''
			name = ''
			date = ''
			stream = ''
			icon = ''
			line = data[j]
			tmp = 'rel="'
			if tmp in line:
				stream = line.split(tmp)[1].split('"')[0]
			tmp = "<img class=\"vid_view\" src=\""
			if tmp in line:
				icon = line.split(tmp)[1].split("\" />")[0]
			tmp = "<p class=\"titleshort\">"
			if tmp in line:
				short = line.split(tmp)[1].split("</p>")[0]
			tmp = "<p class=\"title\">"
			if tmp in line:
				name = line.split(tmp)[1].split("</p>")[0]
			tmp = "<p class=\"date_time bottom\">"
			if tmp in line:
				date = line.split(tmp)[1].split("</p>")[0]
			if stream and date and name and short and icon:
				icon_type = self.getIconType(icon)
				weekList.append((date, name, short, channel, stream, icon, icon_type, False))
			j = j + 1

	def sbsGetProgramList(self, progList):
		out = wgetUrl('%s/stations/%s/pages/kijk' % (self.SBS_BASE_URL, self.channel))
		tmp = out.split('\\n')
		for x in tmp:
			name = ''
			date = ''
			stream = ''
			icon = ''
			icon_type = ''
			if '<li ><a href=\\\"javascript:SBS.SecondScreen.Utils.loadPage(\'kijkdetail?videoId=' in x:
				name = x.split('>')[2].split('<')[0]
				stream = x.split('>')[1].split('videoId=')[1].split('\'')[0]
				progList.append((date, name, '', '', stream, icon, icon_type, False))

	def sbsGetEpisodeList(self, episodeList, uid):
		out = wgetUrl('%s/stations/%s/pages/kijkdetail?videoId=%s' % (self.SBS_BASE_URL, self.channel, uid))
		data = out.split('\\n')
		name = ''
		date = ''
		stream = ''
		icon = ''
		icon_type = ''
		for x in data:
			tmp = '<a href=\\"javascript:SBS.SecondScreen.Utils.loadPage(\'kijkdetail?videoId='
			if tmp in x and '<li' not in x:
				stream = x.split(tmp)[1].split('\'')[0]
			tmp = '<p class=\\"program\\">'
			if tmp in x:
				name = x.split(tmp)[1].split('<')[0]
			tmp = '<img src=\\"'
			if tmp in x:
				icon = x.split(tmp)[1].split('\\\"')[0].replace('\\', '')
			if stream != '' and name != '' and icon != '':
				icon_type = self.getIconType(icon)
				episodeList.append((date, name, '', '', stream, icon, icon_type, False))
				name = ''
				date = ''
				stream = ''
				icon = ''
				icon_type = ''

	def sbsGetMediaUrl(self, uid):
		out = wgetUrlRefer('%s%s' % (self.EMBED_BASE_URL, uid), '%s/kijkframe.php?videoId=%sW&width=868&height=488' % (self.SBS_BASE_URL, uid))
		data = out.split('\n')
		myexp = ''
		id = ''
		key = ''
		vplayer = ''
		oldBW = '1'
		BW = ''
		stream = ''
		for x in data:
			tmp = '\"myExperience'
			if tmp in x:
				myexp = x.split(tmp)[1].split('\\')[0]
			tmp = 'param name=\\\"playerID\\\" value=\\\"'
			if tmp in x:
				id = x.split(tmp)[1].split('\\')[0]
			tmp = '<param name=\\\"playerKey\\\" value=\\\"'
			if tmp in x:
				key = x.split(tmp)[1].split('\\')[0]
			tmp = '<param name=\\\"@videoPlayer\\\" value=\\\"'
			if tmp in x:
				vplayer = x.split('<param name=\\\"@videoPlayer\\\" value=\\\"')[1].split('\\')[0]
		url = ''
		if myexp != '' and id != '' and key != '' and vplayer != '':
			target = "http://c.brightcove.com/services/viewer/htmlFederated?&width=868&height=488&flashID=myExperience%s&bgcolor=%%23FFFFFF&playerID=%s&playerKey=%s&isVid=true&isUI=true&dynamicStreaming=true&wmode=opaque&%%40videoPlayer=%s&branding=sbs&playertitle=true&autoStart=&debuggerID=&refURL=%s/kijkframe.php?videoId=%s&width=868&height=488" % (myexp, id, key, vplayer, self.SBS_BASE_URL, uid)
			out = wgetUrlRefer(target, '%s%s' % (self.EMBED_BASE_URL, uid))
			tmp = out.split('{')
			for x in tmp:
				if 'defaultURL\":' in x and 'defaultURL\":null' not in x:
					url = x.split('defaultURL\":\"')[1].split('\"')[0].replace('\\', '')
		return url

	def getIconType(self, data):
		tmp = ".png"
		if tmp in data:
			return tmp
		tmp = ".gif"
		if tmp in data:
			return tmp
		tmp = ".jpg"
		if tmp in data:
			return tmp
		return ""

def main(session, **kwargs):
	session.open(OpenUgSetupScreen)

def Plugins(**kwargs):

	return [PluginDescriptor(name = "Open uitzending gemist", description = _("Watch uitzending gemist"), where = PluginDescriptor.WHERE_PLUGINMENU, icon="oe-alliance.png", fnc = main),
			PluginDescriptor(name = "Open uitzending gemist", description = _("Watch uitzending gemist"), where = PluginDescriptor.WHERE_EXTENSIONSMENU, fnc = main)]

