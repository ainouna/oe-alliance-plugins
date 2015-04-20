from .. import log
import os, codecs, re
import xml.dom.minidom
from Components.config import config

class Tools():
	def parseXML(self, filename):
		try:
			tool = open(filename, "r")
		except Exception, e:
			#print>>log, "[Tools] Cannot open %s: %s" % (filename, e)
			return None

		try:
			dom = xml.dom.minidom.parse(tool)
		except Exception, e:
			print>>log, "[Tools] XML parse error (%s): %s" % (filename, e)
			tool.close()
			return None

		tool.close()
		return dom
		
	def customLCN(self, services, section_identifier, current_bouquet_key):
		custom_dir = os.path.dirname(__file__) + "/../custom"
		is_sorted = False
		
		for number in services["video"]:
			if number == services["video"][number]["service_id"]:
				continue
			is_sorted = True
			break
			
		for type in ["video", "radio"]:
			skipextrachannels = 0

			# Write Example CustomLCN file
			xmlout = open(custom_dir + "/EXAMPLE_" + ("sd" if current_bouquet_key.startswith('sd') else "hd") + "_" + section_identifier + "_Custom" + ("radio" if type == "radio" else "") + "LCN.xml", "w")
			xmlout.write("<custom>\n\t<include>yes</include>\n\t<lcnlist>\n")
			numbers = sorted(services[type].keys())
			for number in numbers:
				servicename = unicode(services[type][number]["service_name"], errors='ignore')
				xmlout.write("\t\t<configuration lcn=\"%d\" channelnumber=\"%d\" description=\"%s\"></configuration>\n" % (
					number,
					number,
					servicename.replace("&","+")
					))
			xmlout.write("\t</lcnlist>\n</custom>\n")
			xmlout.close()
		
			# Read CustomLCN file
			customfile = custom_dir + "/" + ("sd" if current_bouquet_key.startswith('sd') else "hd") + "_" + section_identifier + "_Custom" + ("radio" if type == "radio" else "") + "LCN.xml"
			dom = self.parseXML(customfile)
			if dom is None:
				print>>log, "[Tools] No custom " + type + " LCN file."
			elif dom.documentElement.nodeType == dom.documentElement.ELEMENT_NODE and dom.documentElement.tagName == "custom":
				customlcndict = {}
				for node in dom.documentElement.childNodes:
					if node.nodeType != node.ELEMENT_NODE:
						continue
					if node.tagName == "include":
						node.normalize()
						if len(node.childNodes) == 1 and node.childNodes[0].nodeType == node.TEXT_NODE:
							if node.childNodes[0].data.encode("utf-8") == 'no' or not config.autobouquetsmaker.showextraservices.value:
								skipextrachannels = 1
					if node.tagName == "lcnlist":
						for node2 in node.childNodes:
							if node2.nodeType == node2.ELEMENT_NODE and node2.tagName == "configuration":
								lcn = 0
								channelnumber = 0
								for i in range(0, node2.attributes.length):
									if node2.attributes.item(i).name == "lcn":
										lcn = int(node2.attributes.item(i).value)
									elif node2.attributes.item(i).name == "channelnumber":
										channelnumber = int(node2.attributes.item(i).value)
								if channelnumber and lcn:
									customlcndict[channelnumber] = lcn
	
				temp_services = {}
				extra_services = {}
				
				# add services from CustomLCN file
				for number in services[type]:
					if number in customlcndict and customlcndict[number] not in temp_services:
						temp_services[customlcndict[number]] = services[type][number]
					else:
						extra_services[number] = services[type][number]

				# add services not in CustomLCN file to correct lcn positions if slots are vacant
				if is_sorted:
					for number in extra_services.keys():
						if number not in temp_services: # CustomLCN has priority
							temp_services[number] = extra_services[number]
							del extra_services[number]
				
				#add any remaining services to the end of list
				if is_sorted or skipextrachannels == 0:
					lastlcn = len(temp_services) and max(temp_services.keys())
					newservices = []
					for number in extra_services:
						temp_services[lastlcn + 1] = extra_services[number]
						lastlcn += 1
						newservices.append(number)
					print>>log, "[Tools] New " + type + " services %s" % (str(newservices))
				
				services[type] = temp_services
			
		return services
		
	def customtransponder(self, provider_key):
		customtransponderdict = {}
		custom_dir = os.path.dirname(__file__) + "/../custom"

		# Read custom file
		print>>log, "[Tools] Transponder provider name", provider_key
		customfile = custom_dir + "/" + provider_key + "_Custom_transponder.xml"
		dom = self.parseXML(customfile)
		if dom is None:
			print>>log, "[Tools] No custom transponder file."
		elif dom.documentElement.nodeType == dom.documentElement.ELEMENT_NODE and dom.documentElement.tagName == "custom":
			j = 0
			for node in dom.documentElement.childNodes:
				if node.nodeType != node.ELEMENT_NODE:
					continue
				if node.tagName == "transponderlist":
					for node2 in node.childNodes:
						if node2.nodeType == node2.ELEMENT_NODE and node2.tagName == "configuration":
							customtransponderdict[j] = {}
							for i in range(0, node2.attributes.length):
								if node2.attributes.item(i).name == "key":
									customtransponderdict[j]["key"] = node2.attributes.item(i).value
								elif node2.attributes.item(i).name == "transport_stream_id":
									customtransponderdict[j]["transport_stream_id"] = int(node2.attributes.item(i).value, 16)
								elif node2.attributes.item(i).name == "frequency":
									customtransponderdict[j]["frequency"] = int(node2.attributes.item(i).value)
								elif node2.attributes.item(i).name == "bandwidth":
									customtransponderdict[j]["bandwidth"] = int(node2.attributes.item(i).value)
								elif node2.attributes.item(i).name == "code_rate_hp":
									customtransponderdict[j]["code_rate_hp"] = int(node2.attributes.item(i).value)
								elif node2.attributes.item(i).name == "code_rate_lp":
									customtransponderdict[j]["code_rate_lp"] = int(node2.attributes.item(i).value)
								elif node2.attributes.item(i).name == "modulation":
									customtransponderdict[j]["modulation"] = int(node2.attributes.item(i).value)
								elif node2.attributes.item(i).name == "transmission_mode":
									customtransponderdict[j]["transmission_mode"] = int(node2.attributes.item(i).value)
								elif node2.attributes.item(i).name == "guard_interval":
									customtransponderdict[j]["guard_interval"] = int(node2.attributes.item(i).value)
								elif node2.attributes.item(i).name == "hierarchy":
									customtransponderdict[j]["hierarchy"] = int(node2.attributes.item(i).value)
								elif node2.attributes.item(i).name == "inversion":
									customtransponderdict[j]["inversion"] = int(node2.attributes.item(i).value)
								elif node2.attributes.item(i).name == "flags":
									customtransponderdict[j]["flags"] = int(node2.attributes.item(i).value)
								elif node2.attributes.item(i).name == "system":
									customtransponderdict[j]["system"] = int(node2.attributes.item(i).value)
								elif node2.attributes.item(i).name == "plpid":
									customtransponderdict[j]["plpid"] = int(node2.attributes.item(i).value)
							j += 1

		return customtransponderdict
		
	def clearsections(self, services, sections, bouquettype, servicetype):
		# bouquettype = HD, FTAHD, FTA
		# servicetype = video, radio
		if len(sections) == 1:
			return sections
			
		active_sections = {}
		for key in services[servicetype].keys():
			if ("FTA" not in bouquettype or services[servicetype][key]["free_ca"] == 0) and ("HD" not in bouquettype or services[servicetype][key]["service_type"] >= 17):
				section_number = max((x for x in sections if int(x) <= key))
				if section_number not in active_sections:
					active_sections[section_number] = sections[section_number]
		if active_sections:
			return active_sections
		return sections